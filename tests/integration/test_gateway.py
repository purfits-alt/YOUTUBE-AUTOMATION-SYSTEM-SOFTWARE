"""AI Provider Gateway against fake providers (COST_CONTROL_SPEC §8, SYSTEM_ARCHITECTURE §4-H)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from tests.integration.conftest import Env
from tubeforge.db.ids import uuid7
from tubeforge.db.models import (
    Channel,
    KillSwitch,
    Notification,
    ProviderCredential,
    ProviderRegistry,
    SecurityEvent,
    SystemSettings,
    UsageLimit,
    UsageRecord,
)
from tubeforge.gateway import limits, registry
from tubeforge.gateway.adapters import AdapterError, Message, TextRequest, TextResponse
from tubeforge.gateway.core import (
    Gateway,
    GatewayInvalidOutputError,
    GatewayLimitError,
    GatewayStoppedError,
    GatewayUnavailableError,
)
from tubeforge.secrets import MemoryStore, SecretBox

pytestmark = pytest.mark.integration

GEMINI = "gemini:gemini-3.5-flash-lite"
GROQ = "groq:openai/gpt-oss-20b"
LOCAL = "ollama:qwen2.5:1.5b"
PAID = "gemini:gemini-3.1-pro-preview"
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
HELLO = [Message("user", "Say hello as JSON")]
SCHEMA = {"type": "object", "required": ["greeting"], "properties": {"greeting": {"type": "string"}}}


class FakeProvider:
    def __init__(self, family: str, needs_key: bool = True) -> None:
        self.family = family
        self.hosts: frozenset[str] = frozenset()
        self.needs_key = needs_key
        self.calls: list[tuple[TextRequest, str | None]] = []
        self.replies: list[str | Exception] = []

    def text(self, request: TextRequest, api_key: str | None) -> TextResponse:
        self.calls.append((request, api_key))
        reply = self.replies.pop(0) if self.replies else f'{{"greeting": "hi from {self.family}"}}'
        if isinstance(reply, Exception):
            raise reply
        return TextResponse(reply, 12, 8)


@pytest.fixture
def box() -> SecretBox:
    b = SecretBox(MemoryStore())
    b.ensure_master_key()
    return b


@pytest.fixture
def db(env: Env) -> Iterator[Session]:
    engine = create_engine(env.db_url)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def fakes() -> dict[str, FakeProvider]:
    return {
        "gemini": FakeProvider("gemini"),
        "groq": FakeProvider("groq"),
        "ollama": FakeProvider("ollama", False),
    }


@pytest.fixture
def gw(db: Session, box: SecretBox, fakes: dict[str, FakeProvider]) -> Gateway:
    registry.set_family_key(db, box, "gemini", "AIza-test-key")
    registry.set_family_key(db, box, "groq", "gsk_test")
    db.commit()
    return Gateway(box, adapters=fakes)  # type: ignore[arg-type]


def _limit(
    db: Session,
    code: str,
    value: int,
    metric: str = "REQUESTS",
    scope: str = "GLOBAL",
    ref: str | None = None,
) -> None:
    db.query(UsageLimit).filter(
        UsageLimit.provider_code == code, UsageLimit.metric == metric, UsageLimit.scope == scope
    ).delete()
    db.add(
        UsageLimit(
            id=uuid7(),
            provider_code=code,
            scope=scope,
            scope_ref=ref,
            metric=metric,
            period="DAY",
            limit_value=value,
        )
    )
    db.commit()


def _channel(db: Session, **kw: Any) -> Channel:
    ch = Channel(id=uuid7(), name="G", state="ACTIVE", content_language="en", **kw)
    db.add(ch)
    db.commit()
    return ch


def call(gw: Gateway, db: Session, chain: list[str], **kw: Any) -> Any:
    return gw.text(
        db,
        task="hello",
        messages=HELLO,
        schema=kw.pop("schema", SCHEMA),
        chain=chain,
        now=NOW,
        use_cache=kw.pop("use_cache", False),
        **kw,
    )


# --------------------------------------------------------------------------------------- limits
def test_provider_pauses_at_its_limit_and_the_fallback_is_used(
    gw: Gateway, db: Session, fakes: dict[str, FakeProvider]
) -> None:
    """COST_CONTROL_SPEC §8 / US-12.2: limit 3/day → the 4th call is LIMIT, owner notified, fallback used."""
    _limit(db, GEMINI, 3)
    for _ in range(3):
        assert call(gw, db, [GEMINI, GROQ]).provider_code == GEMINI
    fourth = call(gw, db, [GEMINI, GROQ])
    assert fourth.provider_code == GROQ and "limit (3) reached" in fourth.skipped[0]
    assert len(fakes["gemini"].calls) == 3
    note = db.scalars(select(Notification).where(Notification.event_type == "provider.limit")).one()
    assert GEMINI in note.body
    # Without a fallback the task must wait until the reset (midnight Pacific).
    with pytest.raises(GatewayLimitError) as exc:
        call(gw, db, [GEMINI])
    assert exc.value.resume_at == datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
    assert (
        db.scalar(
            select(func.count()).select_from(Notification).where(Notification.event_type == "provider.limit")
        )
        == 1
    )


def test_usage_is_reserved_then_settled(gw: Gateway, db: Session) -> None:
    call(gw, db, [GEMINI])
    key = limits.period_key("DAY", limits.PT, NOW)
    assert limits.used(db, GEMINI, "REQUESTS", key) == 1
    assert limits.used(db, GEMINI, "TOKENS", key) == 20  # actual (12 in + 8 out), the estimate was released
    kinds = {r.kind for r in db.scalars(select(UsageRecord).where(UsageRecord.provider_code == GEMINI))}
    assert kinds == {"RESERVE", "SETTLE", "RELEASE"}


def test_task_and_channel_limits(gw: Gateway, db: Session) -> None:
    ch = _channel(db)
    _limit(db, GEMINI, 1, scope="TASK", ref="hello")
    call(gw, db, [GEMINI])
    with pytest.raises(GatewayLimitError):
        call(gw, db, [GEMINI])
    assert (
        gw.text(db, task="seo", messages=HELLO, chain=[GEMINI], now=NOW, use_cache=False).provider_code
        == GEMINI
    )
    _limit(db, GROQ, 1, scope="CHANNEL", ref=str(ch.id))
    call(gw, db, [GROQ], channel_id=ch.id)
    with pytest.raises(GatewayLimitError):
        call(gw, db, [GROQ], channel_id=ch.id)
    call(gw, db, [GROQ])  # other channels are not affected


def test_concurrent_calls_never_exceed_the_limit(gw: Gateway, env: Env, db: Session) -> None:
    _limit(db, GEMINI, 5)
    engine = create_engine(env.db_url, pool_size=15)
    ok: list[int] = []
    barrier = threading.Barrier(12)

    def worker() -> None:
        with Session(engine) as s:
            barrier.wait()
            try:
                gw.text(s, task="hello", messages=HELLO, chain=[GEMINI], now=NOW, use_cache=False)
                ok.append(1)
            except GatewayLimitError:
                pass

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    engine.dispose()
    assert len(ok) == 5


# -------------------------------------------------------------------------------------- policy
def test_paid_provider_is_refused_below_step_two(gw: Gateway, db: Session) -> None:
    row = db.get_one(ProviderRegistry, PAID)
    row.enabled, row.paid_activation_step = True, 1
    db.commit()
    with pytest.raises(GatewayUnavailableError) as exc:
        call(gw, db, [PAID])
    assert "not activated" in exc.value.reasons[0]
    row.paid_activation_step = 2
    row.limits = {"price_in_per_mtok_minor": 100, "price_out_per_mtok_minor": 400}
    db.commit()
    from tubeforge.gateway import paid

    paid.set_cap(db, scope="PAID_PROVIDER", provider_code=PAID, cap_minor=500, now=NOW)
    db.commit()
    assert call(gw, db, [PAID]).provider_code == PAID


def test_local_only_channel_uses_only_providers_that_do_not_train(gw: Gateway, db: Session) -> None:
    ch = _channel(db, local_only=True)
    res = call(gw, db, [GEMINI, GROQ, LOCAL], channel_id=ch.id)
    assert res.provider_code == LOCAL
    assert any("local-only" in s for s in res.skipped) and len(res.skipped) == 2


def test_licence_rules_for_monetised_channels(gw: Gateway, db: Session) -> None:
    ch = _channel(db, is_monetised=True)
    db.get_one(ProviderRegistry, GEMINI).commercial_use = "NO"
    db.get_one(ProviderRegistry, GROQ).commercial_use = "REVIEW"
    db.commit()
    res = call(gw, db, [GEMINI, GROQ, LOCAL], channel_id=ch.id)
    assert res.provider_code == LOCAL
    assert "commercial use" in res.skipped[0] and "review" in res.skipped[1]


def test_missing_key_disabled_provider_and_kill_switch_are_skipped(
    gw: Gateway, db: Session, env: Env
) -> None:
    db.query(ProviderCredential).filter(ProviderCredential.provider_code == GEMINI).delete()
    db.get_one(ProviderRegistry, GROQ).enabled = False
    db.add(KillSwitch(id=uuid7(), scope="PROVIDER", target_id="ollama", reason="t", set_by=env.owner.id))
    db.commit()
    with pytest.raises(GatewayUnavailableError) as exc:
        call(gw, db, [GEMINI, GROQ, LOCAL])
    assert exc.value.reasons == [
        f"{GEMINI}: no API key entered",
        f"{GROQ} is disabled",
        f"{LOCAL}: kill switch",
    ]


def test_emergency_stop_blocks_every_call(gw: Gateway, db: Session, fakes: dict[str, FakeProvider]) -> None:
    db.get_one(SystemSettings, 1).emergency_stop = True
    db.commit()
    with pytest.raises(GatewayStoppedError):
        call(gw, db, [LOCAL])
    assert fakes["ollama"].calls == []


# ------------------------------------------------------------------------- cache / schema / errors
def test_cache_hit_needs_no_call_and_no_quota(
    gw: Gateway, db: Session, fakes: dict[str, FakeProvider]
) -> None:
    first = call(gw, db, [GEMINI], use_cache=True)
    second = call(gw, db, [GEMINI], use_cache=True)
    assert not first.cached and second.cached and second.data == first.data
    assert len(fakes["gemini"].calls) == 1
    assert limits.used(db, GEMINI, "REQUESTS", limits.period_key("DAY", limits.PT, NOW)) == 1


def test_one_repair_then_failure(gw: Gateway, db: Session, fakes: dict[str, FakeProvider]) -> None:
    fakes["gemini"].replies = ['{"wrong": 1}', '{"greeting": "fixed"}']
    res = call(gw, db, [GEMINI])
    assert res.repaired and res.data == {"greeting": "fixed"}
    repair_prompt = fakes["gemini"].calls[1][0].messages[-1].content
    assert "greeting" in repair_prompt and "is a required property" in repair_prompt
    fakes["gemini"].replies = ["not json at all", '{"still": "wrong"}']
    with pytest.raises(GatewayInvalidOutputError):
        call(gw, db, [GEMINI])
    assert limits.used(db, GEMINI, "REQUESTS", limits.period_key("DAY", limits.PT, NOW)) == 4


def test_provider_errors_fall_back(gw: Gateway, db: Session, fakes: dict[str, FakeProvider]) -> None:
    fakes["gemini"].replies = [AdapterError("TRANSIENT", 503, "overloaded")]
    fakes["groq"].replies = [AdapterError("AUTH", 401, "the API key was not accepted")]
    res = call(gw, db, [GEMINI, GROQ, LOCAL])
    assert res.provider_code == LOCAL and len(res.skipped) == 2
    assert (
        db.scalars(select(Notification).where(Notification.event_type == "provider.auth")).first() is not None
    )


def test_paid_indicator_switches_the_provider_off(
    gw: Gateway, db: Session, fakes: dict[str, FakeProvider]
) -> None:
    """A32: billing wording in a response → provider disabled + kill switch + CRITICAL alert."""
    fakes["gemini"].replies = [
        AdapterError("PAID_INDICATOR", 403, "the provider mentions billing or payment")
    ]
    res = call(gw, db, [GEMINI, LOCAL])
    assert res.provider_code == LOCAL
    assert db.get_one(ProviderRegistry, GEMINI).enabled is False
    assert db.scalars(
        select(KillSwitch).where(KillSwitch.target_id == GEMINI, KillSwitch.active.is_(True))
    ).one()
    note = db.scalars(select(Notification).where(Notification.event_type == "cost.paid_indicator")).one()
    assert note.severity == "CRITICAL"
    assert db.scalars(select(SecurityEvent).where(SecurityEvent.kind == "PAID_INDICATOR")).one()


def test_keys_are_encrypted_per_row(gw: Gateway, db: Session, box: SecretBox) -> None:
    rows = db.scalars(
        select(ProviderCredential).where(ProviderCredential.provider_code.like("gemini:%"))
    ).all()
    assert len(rows) == 5 and all(b"AIza-test-key" not in r.secret_enc for r in rows)
    assert registry.api_key(db, box, GEMINI) == "AIza-test-key"
    assert not registry.has_key(db, "groq:unknown") and registry.has_key(db, LOCAL)


def test_unknown_or_unlisted_provider(gw: Gateway, db: Session) -> None:
    with pytest.raises(GatewayUnavailableError) as exc:
        call(gw, db, ["mystery:model"])
    assert exc.value.reasons == ["mystery:model: not in the registry"]
