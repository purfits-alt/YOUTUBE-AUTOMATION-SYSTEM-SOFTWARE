"""The AI Provider Gateway — the only path to model providers (SYSTEM_ARCHITECTURE §4-H).

For every call, along the task's provider chain, the first provider that can answer is used:

1. Emergency Stop (stops everything) and provider kill switches (skip that provider)
2. registry policy: enabled; Tier P only after two-step activation; commercial-use licence for
   monetised channels; no data-training providers for local-only channels; key present
3. cache lookup (provider + model + prompt version + input)
4. atomic usage reservation against every applicable limit — at a limit the owner is told and the
   next provider in the chain is tried (G7/G8)
5. call with a timeout
6. JSON-schema validation and **one** repair attempt
7. settle the actual usage; 8. log (no prompt text) and return

When every provider is at its limit the caller gets :class:`GatewayLimitError` with the earliest reset
time (the task waits: WAITING_QUOTA). Usage records are committed by the gateway itself, so other
workers see reservations immediately: call it with a session you are happy to have committed.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import jsonschema_rs
from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.audit import SYSTEM, record, security_event
from tubeforge.db.ids import uuid7
from tubeforge.db.models import Channel, KillSwitch, ProviderRegistry, SystemSettings
from tubeforge.gateway import cache, indicators, limits, paid, registry
from tubeforge.gateway.adapters import AdapterError, Message, TextAdapter, TextRequest, TextResponse
from tubeforge.gateway.adapters.gemini import GeminiAdapter
from tubeforge.gateway.adapters.groq import GroqAdapter
from tubeforge.gateway.adapters.ollama import OllamaAdapter
from tubeforge.logging import get_logger
from tubeforge.notifications import notify_owners, owner_ids
from tubeforge.orchestrator import controls
from tubeforge.secrets import SecretBox

log = get_logger("tubeforge.gateway")

LOCAL = "ollama:qwen2.5:1.5b"
# Fallback chains per task type (owner-editable in Settings › provider_chains; agents may override).
DEFAULT_CHAINS: dict[str, list[str]] = {
    "default": ["gemini:gemini-3.8-flash", "groq:openai/gpt-oss-120b", LOCAL],
    "script_draft": ["gemini:gemini-3.8-flash", "groq:openai/gpt-oss-120b", LOCAL],
    "research": ["gemini:gemini-3.8-flash", "groq:openai/gpt-oss-120b", LOCAL],
    "ideas": ["gemini:gemini-3.6-flash", "groq:openai/gpt-oss-120b", LOCAL],
    "seo": ["gemini:gemini-3.5-flash-lite", "groq:openai/gpt-oss-20b", LOCAL],
    "classify": ["gemini:gemini-3.5-flash-lite", "groq:openai/gpt-oss-20b", LOCAL],
    "hello": ["gemini:gemini-3.5-flash-lite", "groq:openai/gpt-oss-20b", LOCAL],
}
REPAIR_PROMPT = (
    "Your previous answer was not valid JSON for the required schema. Problems: {errors}. "
    "Answer again with ONLY the corrected JSON object, nothing else."
)


class GatewayError(Exception):
    pass


class GatewayStoppedError(GatewayError):
    """Emergency Stop is on: nothing is sent to any provider."""


class GatewayLimitError(GatewayError):
    """Every provider in the chain is at a limit (or skipped); retry at ``resume_at``."""

    def __init__(self, resume_at: datetime, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.resume_at = resume_at
        self.reasons = reasons


class GatewayUnavailableError(GatewayError):
    """No provider in the chain could be used (policy, keys, errors)."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class GatewayInvalidOutputError(GatewayError):
    """The answer failed the schema twice (original + one repair)."""


@dataclass
class GatewayResult:
    provider_code: str
    text: str
    data: Any  # parsed JSON when a schema was given
    tokens_in: int
    tokens_out: int
    cached: bool
    repaired: bool
    duration_ms: int
    skipped: list[str] = field(default_factory=list)


def estimate_tokens(system: str | None, messages: Sequence[Message], max_output: int) -> int:
    chars = len(system or "") + sum(len(m.content) for m in messages)
    return chars // 4 + 1 + max_output


def chain_for(db: Session, task: str) -> list[str]:
    settings = db.get(SystemSettings, 1)
    configured = ((settings.settings if settings else None) or {}).get("provider_chains", {})
    chain = (
        configured.get(task)
        or DEFAULT_CHAINS.get(task)
        or configured.get("default")
        or DEFAULT_CHAINS["default"]
    )
    return [str(c) for c in chain]


class Gateway:
    def __init__(self, box: SecretBox, adapters: dict[str, TextAdapter] | None = None) -> None:
        self.box = box
        self.adapters: dict[str, TextAdapter] = adapters or {
            "gemini": GeminiAdapter(),
            "groq": GroqAdapter(),
            "ollama": OllamaAdapter(),
        }

    # ------------------------------------------------------------------------------------- text
    def text(
        self,
        db: Session,
        *,
        task: str,
        messages: Sequence[Message],
        system: str | None = None,
        schema: dict[str, Any] | None = None,
        channel_id: uuid.UUID | None = None,
        agent_run_id: uuid.UUID | None = None,
        agent_code: str | None = None,
        prompt_version: str = "v1",
        max_output_tokens: int = 1024,
        temperature: float = 0.3,
        chain: Sequence[str] | None = None,
        use_cache: bool = True,
        now: datetime | None = None,
    ) -> GatewayResult:
        now = now or datetime.now(UTC)
        db.commit()  # read committed controls, and keep our usage commits separate from caller work
        if controls.stop_reason(db) == "EMERGENCY_STOP":
            raise GatewayStoppedError("Emergency Stop is on")
        if agent_code and controls.stop_reason(db, agent_code=agent_code):
            raise GatewayStoppedError(f"agent {agent_code} is switched off")
        validator = jsonschema_rs.validator_for(schema) if schema else None
        channel = db.get(Channel, channel_id) if channel_id else None
        skipped: list[str] = []
        limit_resets: list[datetime] = []
        est_in = estimate_tokens(system, messages, 0)
        for code in chain or chain_for(db, task):
            provider = db.get(ProviderRegistry, code)
            if provider is None:
                skipped.append(f"{code}: not in the registry")
                continue
            if controls.stop_reason(db, provider_code=code) or controls.stop_reason(
                db, provider_code=registry.family(code)
            ):
                skipped.append(f"{code}: kill switch")
                continue
            blocked = registry.policy_block(provider, channel) or self._paid_block(
                db, provider, est_in, max_output_tokens, now
            )
            if blocked:
                skipped.append(blocked)
                continue
            adapter = self.adapters.get(registry.family(code))
            if adapter is None:
                skipped.append(f"{code}: no adapter")
                continue
            key = registry.api_key(db, self.box, code) if adapter.needs_key else None
            if adapter.needs_key and not key:
                skipped.append(f"{code}: no API key entered")
                continue
            request = TextRequest(
                model=registry.model(code),
                messages=tuple(messages),
                system=system,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                json_mode=schema is not None,
            )
            ckey = cache.cache_key(code, prompt_version, {"req": _req_dict(request), "schema": schema})
            if use_cache and (hit := cache.get(db, ckey, now=now)) is not None:
                db.commit()
                log.info("gateway.cache_hit", provider=code, task=task)
                return GatewayResult(code, hit["text"], hit.get("data"), 0, 0, True, False, 0, skipped)
            try:
                return self._call(
                    db,
                    adapter,
                    provider,
                    request,
                    key,
                    validator,
                    task,
                    channel_id,
                    agent_run_id,
                    ckey,
                    use_cache,
                    skipped,
                    now,
                )
            except limits.LimitReached as exc:
                db.rollback()
                limit_resets.append(exc.resets_at)
                skipped.append(
                    f"{code}: {exc.metric.lower()} per {exc.period.lower()} limit ({exc.limit}) reached"
                )
                self._notify_limit(db, code, exc.resets_at, exc.period, now)
            except AdapterError as exc:
                skipped.append(f"{code}: {exc.kind.lower()} — {exc.detail}")
                if exc.kind == "LIMIT":
                    resets = now + timedelta(seconds=exc.retry_after_s or 60)
                    limit_resets.append(resets)
                    self._notify_limit(db, code, resets, "provider", now)
                elif exc.kind == "PAID_INDICATOR":
                    self._paid_indicator(db, provider, exc)
                elif exc.kind == "AUTH":
                    self._notify(
                        db,
                        code,
                        "provider.auth",
                        "WARNING",
                        "An AI provider refused the API key",
                        f"{code}: {exc.detail}. Check the key in Cost & Usage.",
                    )
        if limit_resets:
            raise GatewayLimitError(min(limit_resets), skipped)
        raise GatewayUnavailableError(skipped)

    @staticmethod
    def _paid_block(
        db: Session, provider: ProviderRegistry, est_in: int, max_output: int, now: datetime
    ) -> str | None:
        """Tier P: a known price and enough of this month's budget for the worst case of this call
        (estimated input + the full output allowance)."""
        if provider.tier != "P":
            return None
        worst = paid.cost_minor(provider, est_in, max_output)
        if worst is None:
            return f"{provider.code} has no recorded price, so its cost cannot be capped"
        if paid.remaining_minor(db, provider.code, now) < worst:
            return f"{provider.code}: this month's budget is used up"
        return None

    # ------------------------------------------------------------------------------------- call
    def _call(
        self,
        db: Session,
        adapter: TextAdapter,
        provider: ProviderRegistry,
        request: TextRequest,
        key: str | None,
        validator: Any,
        task: str,
        channel_id: uuid.UUID | None,
        agent_run_id: uuid.UUID | None,
        ckey: str,
        use_cache: bool,
        skipped: list[str],
        now: datetime,
    ) -> GatewayResult:
        code = provider.code
        started = time.monotonic()
        response, tokens_in, tokens_out, repaired = self._one(
            db, adapter, code, request, key, task, channel_id, agent_run_id, now
        )
        data: Any = None
        if validator is not None:
            data, errors = _check(validator, response.text)
            if errors:
                repaired = True
                fix = TextRequest(
                    model=request.model,
                    messages=(
                        *request.messages,
                        Message("assistant", response.text[:4000]),
                        Message("user", REPAIR_PROMPT.format(errors="; ".join(errors[:10]))),
                    ),
                    system=request.system,
                    max_output_tokens=request.max_output_tokens,
                    temperature=0.0,
                    json_mode=True,
                )
                response, more_in, more_out, _ = self._one(
                    db, adapter, code, fix, key, task, channel_id, agent_run_id, now
                )
                tokens_in += more_in
                tokens_out += more_out
                data, errors = _check(validator, response.text)
                if errors:
                    log.warning("gateway.invalid_output", provider=code, task=task, errors=errors[:3])
                    raise GatewayInvalidOutputError(
                        f"{code} returned invalid JSON twice: {'; '.join(errors[:3])}"
                    )
        if use_cache:
            cache.put(db, ckey, code, {"text": response.text, "data": data}, now=now)
            db.commit()
        ms = int((time.monotonic() - started) * 1000)
        log.info(
            "gateway.call",
            provider=code,
            task=task,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            ms=ms,
            repaired=repaired,
        )
        return GatewayResult(code, response.text, data, tokens_in, tokens_out, False, repaired, ms, skipped)

    def _one(
        self,
        db: Session,
        adapter: TextAdapter,
        code: str,
        request: TextRequest,
        key: str | None,
        task: str,
        channel_id: uuid.UUID | None,
        agent_run_id: uuid.UUID | None,
        now: datetime,
    ) -> tuple[TextResponse, int, int, bool]:
        estimate = estimate_tokens(request.system, request.messages, request.max_output_tokens)
        res = limits.reserve(
            db,
            code,
            {"REQUESTS": 1, "TOKENS": estimate},
            task=task,
            channel_id=channel_id,
            agent_run_id=agent_run_id,
            now=now,
        )
        db.commit()  # the reservation is visible to every other worker before the slow call
        try:
            response = adapter.text(request, key)
        except AdapterError as exc:
            # The provider answered with an error: the request counts (providers bill every request).
            limits.settle(
                db, res, {"REQUESTS": 1, "TOKENS": 0} if exc.status else {"REQUESTS": 0, "TOKENS": 0}
            )
            db.commit()
            raise
        limits.settle(db, res, {"REQUESTS": 1, "TOKENS": response.tokens_in + response.tokens_out})
        provider = db.get_one(ProviderRegistry, code)
        if provider.tier == "P":
            paid.debit(
                db, provider, paid.cost_minor(provider, response.tokens_in, response.tokens_out) or 0, now=now
            )
        db.commit()
        if (sign := indicators.inspect(provider, response.headers)) is not None:
            self._paid_indicator(db, provider, AdapterError("PAID_INDICATOR", 200, sign))
        return response, response.tokens_in, response.tokens_out, False

    # ---------------------------------------------------------------------------------- alerts
    def _notify(
        self,
        db: Session,
        code: str,
        event: str,
        severity: str,
        title: str,
        body: str,
        window: timedelta = timedelta(hours=6),
    ) -> None:
        notify_owners(
            db,
            event_type=event,
            severity=severity,
            title=title,
            body=body,
            dedup_key=f"{event}:{code}",
            dedup_window=window,
            link="/usage",
        )
        db.commit()

    def _notify_limit(self, db: Session, code: str, resets_at: datetime, period: str, now: datetime) -> None:
        notify_owners(
            db,
            event_type="provider.limit",
            severity="WARNING",
            title="An AI provider reached its limit",
            body=f"{code} reached its {period.lower()} limit. TubeForge uses the next provider in the chain; "
            f"{code} is available again at {resets_at.astimezone(UTC):%Y-%m-%d %H:%M} UTC.",
            dedup_key=f"provider.limit:{code}:{limits.period_key('DAY', limits.PT, now)}",
            dedup_window=timedelta(hours=24),
            link="/usage",
            now=now,
        )
        db.commit()

    def _paid_indicator(self, db: Session, provider: ProviderRegistry, exc: AdapterError) -> None:
        """A32: a sign of a paid or billing path → switch the provider off at once and alert (CRITICAL)."""
        provider.enabled = False
        owners = owner_ids(db)
        if (
            owners
            and db.scalar(
                select(KillSwitch.id).where(
                    KillSwitch.scope == "PROVIDER",
                    KillSwitch.target_id == provider.code,
                    KillSwitch.active.is_(True),
                )
            )
            is None
        ):
            db.add(
                KillSwitch(
                    id=uuid7(),
                    scope="PROVIDER",
                    target_id=provider.code,
                    reason=f"A32 paid indicator: {exc.detail}",
                    set_by=owners[0],
                )
            )
        security_event(
            db, "PAID_INDICATOR", "CRITICAL", details={"provider": provider.code, "status": exc.status}
        )
        record(
            db,
            actor=SYSTEM,
            action="provider.paid_indicator",
            entity_type="provider",
            entity_id=provider.code,
            details={"detail": exc.detail},
        )
        self._notify(
            db,
            provider.code,
            "cost.paid_indicator",
            "CRITICAL",
            "Possible charges: an AI provider was switched off",
            f"{provider.code} answered with billing or payment wording. TubeForge switched it off. "
            "Check that no billing account is linked to that project.",
        )


def _req_dict(r: TextRequest) -> dict[str, Any]:
    return {
        "model": r.model,
        "system": r.system,
        "messages": [[m.role, m.content] for m in r.messages],
        "max": r.max_output_tokens,
        "temperature": r.temperature,
        "json": r.json_mode,
    }


def _check(validator: Any, text: str) -> tuple[Any, list[str]]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        candidate = candidate[candidate.find("{") :] if "{" in candidate else candidate
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        return None, [f"not JSON ({exc.msg})"]
    return data, [_describe(e) for e in _leaf_errors(validator.iter_errors(data), data)]


def _leaf_errors(errors: Any, data: Any) -> list[Any]:
    """Specific errors instead of "<the whole answer> is not valid under any of the given schemas".

    Agent schemas are ``oneOf: [task schema, refusal]``. When an answer fails both, report the
    errors of the branch it was aiming for (the refusal branch only if it has a "refusal" key), so
    the repair request can name the fields to fix.
    """
    out: list[Any] = []
    for e in errors:
        branches = getattr(e.kind, "context", None) if e.kind.name in ("oneOf", "anyOf") else None
        if branches:
            wants_refusal = isinstance(data, dict) and "refusal" in data
            out += _leaf_errors(branches[-1] if wants_refusal else branches[0], data)
        else:
            out.append(e)
    return out


def _describe(e: Any) -> str:
    where = "/".join(map(str, e.instance_path)) or "(root)"
    message = str(e.message)
    return f"{where}: {message if len(message) <= 200 else message[:197] + '...'}"
