"""Agent runner (HELLO), two-step paid activation and budgets, A32 monitor (COST_CONTROL_SPEC §8)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from tubeforge_agents.base import run_agent
from tubeforge_agents.hello import HelloAgent
from tubeforge_auditors import a32_cost

from tests.integration.conftest import Env
from tests.integration.test_gateway import GEMINI, LOCAL, PAID, FakeProvider
from tubeforge.audit import Actor
from tubeforge.db.ids import uuid7
from tubeforge.db.models import (
    AgentConfiguration,
    AgentRun,
    CostBudget,
    KillSwitch,
    Notification,
    ProviderRegistry,
    SystemSettings,
    UsageLimit,
)
from tubeforge.gateway import paid, registry
from tubeforge.gateway.adapters import TextRequest, TextResponse
from tubeforge.gateway.core import Gateway
from tubeforge.secrets import MemoryStore, SecretBox

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
HELLO = HelloAgent()


class HelloFake(FakeProvider):
    def __init__(self, family: str, needs_key: bool = True, headers: dict[str, str] | None = None) -> None:
        super().__init__(family, needs_key)
        self.headers = headers or {}

    def text(self, request: TextRequest, api_key: str | None) -> TextResponse:
        self.calls.append((request, api_key))
        reply = (
            self.replies.pop(0)
            if self.replies
            else f'{{"greeting": "Hello from {self.family}", "language": "en"}}'
        )
        if isinstance(reply, Exception):
            raise reply
        return TextResponse(reply, 30, 10, self.headers)


@pytest.fixture
def db(env: Env) -> Iterator[Session]:
    engine = create_engine(env.db_url)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def fakes() -> dict[str, HelloFake]:
    return {"gemini": HelloFake("gemini"), "groq": HelloFake("groq"), "ollama": HelloFake("ollama", False)}


@pytest.fixture
def gw(db: Session, fakes: dict[str, HelloFake]) -> Gateway:
    box = SecretBox(MemoryStore())
    box.ensure_master_key()
    registry.set_family_key(db, box, "gemini", "AIza-test")
    registry.set_family_key(db, box, "groq", "gsk_test")
    db.commit()
    return Gateway(box, adapters=fakes)  # type: ignore[arg-type]


def hello(db: Session, gw: Gateway, name: str = "Ayesha", **kw: object) -> object:
    return run_agent(db, gw, HELLO, {"name": name}, idempotent=bool(kw.pop("idempotent", False)), now=NOW)


# ----------------------------------------------------------------------------------------- agents
def test_hello_agent_runs_and_is_logged(db: Session, gw: Gateway, fakes: dict[str, HelloFake]) -> None:
    outcome = run_agent(db, gw, HELLO, {"name": "Ayesha <ayesha@example.com>"}, now=NOW)
    run = outcome.run
    assert run.status == "SUCCEEDED" and outcome.data == {"greeting": "Hello from gemini", "language": "en"}
    assert (run.provider_code, run.model, run.tokens_in, run.tokens_out) == (
        GEMINI,
        "gemini-3.5-flash-lite",
        30,
        10,
    )
    assert run.input == {"name": "Ayesha <[email]>"}  # redacted in the log
    request = fakes["gemini"].calls[0][0]
    assert request.system and request.system.startswith("You are Hello test agent (T00_HELLO v1.0)")
    assert '<untrusted_source id="name">Ayesha' in request.messages[0].content
    # Idempotent re-run (orchestrated jobs): same input + prompt version → the earlier result, no call.
    again = run_agent(db, gw, HELLO, {"name": "Ayesha <ayesha@example.com>"}, now=NOW)
    assert again.run.id == run.id and len(fakes["gemini"].calls) == 1


def test_owner_demo_limit_two_per_day_then_waits(db: Session, gw: Gateway) -> None:
    """Roadmap demo: limit 2/day → the 3rd run waits and the owner gets a notification."""
    cfg = db.get_one(AgentConfiguration, "T00_HELLO")
    cfg.limits = {**cfg.limits, "calls_per_day": 2}
    db.commit()
    assert hello(db, gw).run.status == "SUCCEEDED"  # type: ignore[attr-defined]
    assert hello(db, gw, "Bilal").run.status == "SUCCEEDED"  # type: ignore[attr-defined]
    third = hello(db, gw, "Chen")
    assert third.run.status == "WAITING_QUOTA" and third.run.error_class == "AGENT_LIMIT"  # type: ignore[attr-defined]
    assert third.resume_at == datetime(2026, 11, 10, 8, 0, tzinfo=UTC)  # type: ignore[attr-defined]
    note = db.scalars(select(Notification).where(Notification.event_type == "agent.limit")).one()
    assert "Hello test agent" in note.body


def test_switching_the_chain_to_the_local_model(
    db: Session, gw: Gateway, fakes: dict[str, HelloFake]
) -> None:
    cfg = db.get_one(AgentConfiguration, "T00_HELLO")
    cfg.provider_chain = [LOCAL]
    db.commit()
    assert hello(db, gw).run.provider_code == LOCAL  # type: ignore[attr-defined]
    assert fakes["gemini"].calls == []


def test_emergency_stop_kill_switch_and_disabled_agent_abort(
    db: Session, gw: Gateway, env: Env, fakes: dict[str, HelloFake]
) -> None:
    db.get_one(SystemSettings, 1).emergency_stop = True
    db.commit()
    stopped = hello(db, gw).run  # type: ignore[attr-defined]
    assert (stopped.status, stopped.error_class) == ("ABORTED", "EMERGENCY_STOP")
    db.get_one(SystemSettings, 1).emergency_stop = False
    db.add(KillSwitch(id=uuid7(), scope="AGENT", target_id="T00_HELLO", reason="t", set_by=env.owner.id))
    db.commit()
    assert hello(db, gw).run.error_class == "KILL_SWITCH_AGENT"  # type: ignore[attr-defined]
    db.execute(KillSwitch.__table__.update().values(active=False))
    db.get_one(AgentConfiguration, "T00_HELLO").enabled = False
    db.commit()
    assert hello(db, gw).run.error_class == "DISABLED"  # type: ignore[attr-defined]
    assert all(not f.calls for f in fakes.values())


def test_refusal_provider_limit_and_bad_output(db: Session, gw: Gateway, fakes: dict[str, HelloFake]) -> None:
    fakes["gemini"].replies = ['{"refusal": {"code": "POLICY", "reason": "That is not a name."}}']
    refused = hello(db, gw).run  # type: ignore[attr-defined]
    assert (refused.status, refused.error_class) == ("FAILED", "REFUSAL")
    assert db.scalars(select(Notification).where(Notification.event_type == "agent.refused")).one()

    cfg = db.get_one(AgentConfiguration, "T00_HELLO")
    cfg.provider_chain = [GEMINI]
    db.query(UsageLimit).filter(UsageLimit.provider_code == GEMINI, UsageLimit.metric == "REQUESTS").update(
        {"limit_value": 1}
    )
    db.commit()
    waiting = hello(db, gw, "Dina")
    assert waiting.run.status == "WAITING_QUOTA" and waiting.run.error_class == "PROVIDER_LIMIT"  # type: ignore[attr-defined]

    db.query(UsageLimit).filter(UsageLimit.provider_code == GEMINI).update({"limit_value": 10_000_000})
    db.commit()
    fakes["gemini"].replies = ['{"greeting": 5}', '{"also": "wrong"}']
    bad = hello(db, gw, "Eve").run  # type: ignore[attr-defined]
    assert (bad.status, bad.error_class, bad.repair_attempted) == ("FAILED", "VALIDATION", True)


# ----------------------------------------------------------------------------------- paid providers
def test_two_step_paid_activation(db: Session, env: Env) -> None:
    owner = Actor("OWNER", str(env.owner.id))
    with pytest.raises(paid.PaidActivationError) as exc:
        paid.step2(db, PAID, phrase=paid.confirm_phrase(PAID), monthly_cap_minor=500, actor=owner)
    assert exc.value.code == "STEP1_REQUIRED"
    paid.step1(db, PAID, actor=owner)
    db.commit()
    with pytest.raises(paid.PaidActivationError) as exc:  # within 60 s of step 1
        paid.step2(db, PAID, phrase=paid.confirm_phrase(PAID), monthly_cap_minor=500, actor=owner)
    assert exc.value.code == "TOO_SOON"
    later = datetime.now(UTC) + timedelta(seconds=61)
    for phrase, cap, code in (
        ("enable paid", 500, "PHRASE_MISMATCH"),
        (paid.confirm_phrase(PAID), 0, "CAP_REQUIRED"),
    ):
        with pytest.raises(paid.PaidActivationError) as exc:
            paid.step2(db, PAID, phrase=phrase, monthly_cap_minor=cap, actor=owner, now=later)
        assert exc.value.code == code
    row = paid.step2(
        db, PAID, phrase=paid.confirm_phrase(PAID), monthly_cap_minor=500, actor=owner, now=later
    )
    db.commit()
    assert (row.paid_activation_step, row.enabled) == (2, True)
    assert paid.remaining_minor(db, PAID, later) == 500
    paid.disable(db, PAID, actor=owner)
    db.commit()
    assert (
        db.get_one(ProviderRegistry, PAID).paid_activation_step,
        db.get_one(ProviderRegistry, PAID).enabled,
    ) == (0, False)


def test_step1_expires_after_30_minutes(db: Session, env: Env) -> None:
    owner = Actor("OWNER", str(env.owner.id))
    paid.step1(db, PAID, actor=owner)
    db.commit()
    with pytest.raises(paid.PaidActivationError) as exc:
        paid.step2(
            db,
            PAID,
            phrase=paid.confirm_phrase(PAID),
            monthly_cap_minor=5,
            actor=owner,
            now=datetime.now(UTC) + timedelta(minutes=31),
        )
    assert exc.value.code == "STEP1_EXPIRED"


def test_paid_calls_are_capped_and_pause_at_the_cap(
    db: Session, gw: Gateway, env: Env, fakes: dict[str, HelloFake]
) -> None:
    row = db.get_one(ProviderRegistry, PAID)
    row.paid_activation_step, row.enabled = 2, True
    db.commit()
    chain = [PAID]
    msg = {"task": "hello", "messages": [], "chain": chain, "use_cache": False}
    from tubeforge.gateway.core import GatewayUnavailableError

    with pytest.raises(GatewayUnavailableError) as exc:  # no recorded price → refused
        gw.text(db, **msg)  # type: ignore[arg-type]
    assert "no recorded price" in exc.value.reasons[0]
    row.limits = {"price_in_per_mtok_minor": 100_000, "price_out_per_mtok_minor": 100_000}
    db.commit()
    with pytest.raises(GatewayUnavailableError) as exc:  # no budget this month → refused
        gw.text(db, **msg)  # type: ignore[arg-type]
    assert "budget is used up" in exc.value.reasons[0]
    paid.set_cap(db, scope="PAID_PROVIDER", provider_code=PAID, cap_minor=110)
    db.commit()
    gw.text(db, task="hello", messages=[], chain=chain, use_cache=False, max_output_tokens=100)  # costs 4
    budget = db.scalars(select(CostBudget).where(CostBudget.provider_code == PAID)).one()
    assert budget.spent_minor == 4
    budget.spent_minor = 108
    db.commit()
    with pytest.raises(GatewayUnavailableError):  # the worst case of this call no longer fits
        gw.text(db, task="hello", messages=[], chain=chain, use_cache=False, max_output_tokens=100)
    budget.spent_minor = 0
    db.commit()
    fakes["gemini"].replies = ['{"greeting": "x", "language": "en"}']
    row.limits = {"price_in_per_mtok_minor": 3_000_000, "price_out_per_mtok_minor": 3_000_000}
    db.commit()
    paid.set_cap(db, scope="PAID_PROVIDER", provider_code=PAID, cap_minor=200)
    db.commit()
    gw.text(db, task="hello", messages=[], chain=chain, use_cache=False, max_output_tokens=10)  # costs 120
    gw.text(
        db, task="hello", messages=[], chain=chain, use_cache=False, max_output_tokens=10
    )  # reaches the cap
    db.expire_all()
    assert db.get_one(ProviderRegistry, PAID).enabled is False
    note = db.scalars(select(Notification).where(Notification.event_type == "cost.cap_reached")).one()
    assert note.severity == "CRITICAL"


def test_paid_tier_sign_in_a_successful_response_switches_the_provider_off(
    db: Session, gw: Gateway, fakes: dict[str, HelloFake]
) -> None:
    fakes["gemini"].headers = {"x-usage-tier": "Tier 1"}
    hello(db, gw)
    db.expire_all()
    assert db.get_one(ProviderRegistry, GEMINI).enabled is False
    assert (
        db.scalars(select(Notification).where(Notification.event_type == "cost.paid_indicator"))
        .one()
        .severity
        == "CRITICAL"
    )


# ------------------------------------------------------------------------------------------------ A32
def test_a32_thresholds_reminders_and_its_own_run_log(db: Session, gw: Gateway) -> None:
    db.query(UsageLimit).filter(UsageLimit.provider_code == GEMINI, UsageLimit.metric == "REQUESTS").update(
        {"limit_value": 10}
    )
    db.commit()
    for i in range(9):
        hello(db, gw, f"N{i}")
    report = a32_cost.scan(db, now=NOW)
    assert f"{GEMINI} REQUESTS 90%" in report.alerts
    line = next(x for x in report.lines if x.subject == GEMINI and x.metric == "REQUESTS")
    assert (line.used, line.limit, line.pct) == (9, 10, 90)
    assert any(x.subject.startswith("YouTube DEFAULT") for x in report.lines)
    a32_cost.scan(db, now=NOW)  # same threshold, same day → no second alert
    alerts = db.scalars(select(Notification).where(Notification.event_type == "usage.alert")).all()
    assert len(alerts) == 1 and alerts[0].severity == "WARNING", [a.title for a in alerts]
    assert db.scalar(select(AgentRun).where(AgentRun.agent_code == "A32_COST_MONITOR").limit(1)) is not None

    db.get_one(ProviderRegistry, LOCAL).verified_at = date(2026, 1, 1)
    db.commit()
    first_of_month = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)
    report = a32_cost.scan(db, now=first_of_month)
    assert LOCAL in report.reverify_due
    kinds = {n.event_type for n in db.scalars(select(Notification))}
    assert {"provider.reverify", "cost.statement_check"} <= kinds
