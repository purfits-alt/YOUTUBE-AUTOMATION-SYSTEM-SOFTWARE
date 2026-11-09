"""Agent framework (AI_AGENT_ARCHITECTURE §1, §3 common rules).

An agent is a task handler: typed input → prompt → Gateway → schema-checked output. The runner
:func:`run_agent` adds what every agent shares:

- configuration from ``agent_configurations`` (enabled, chain, limits, prompt version);
- Emergency Stop and agent kill switch → ABORTED; per-agent daily call/token budgets → WAITING_QUOTA
  with a notification; provider limits (Gateway) → WAITING_QUOTA with the resume time;
- an ``agent_runs`` row with redacted input/output (secrets, e-mail addresses, phone numbers),
  provider, model, tokens, latency, status; a refusal object → FAILED with its reason;
- optional idempotency: the same agent, input and prompt version returns the earlier success.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tubeforge.db.ids import uuid7
from tubeforge.db.models import AgentConfiguration, AgentRun, Channel
from tubeforge.gateway import limits
from tubeforge.gateway.adapters import Message
from tubeforge.gateway.core import (
    Gateway,
    GatewayError,
    GatewayInvalidOutputError,
    GatewayLimitError,
    GatewayStoppedError,
)
from tubeforge.logging import redact_value
from tubeforge.notifications import notify_owners
from tubeforge.orchestrator import controls
from tubeforge_agents.prompting import output_schema, render_system

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
COUNTED = ("RUNNING", "SUCCEEDED", "REPAIRED", "FAILED")


def redact(value: Any) -> Any:
    """Secrets (logging rules) plus e-mail addresses and phone numbers (common logging rule)."""
    value = redact_value(value)
    if isinstance(value, str):
        return PHONE.sub("[phone]", EMAIL.sub("[email]", value))
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value


class AgentTask(ABC):
    """Base class of a model-backed agent. Subclasses set the class attributes and build the prompt."""

    code: ClassVar[str]
    task_type: ClassVar[str] = "default"  # Gateway chain name when the agent has no own chain
    temperature: ClassVar[float] = 0.2
    max_output_tokens: ClassVar[int] = 1024
    input_model: ClassVar[type[BaseModel]]

    @abstractmethod
    def user_message(self, data: BaseModel) -> str:
        """The user turn; untrusted text must go through the ``untrusted`` filter."""

    def context(self, data: BaseModel, channel: Channel | None) -> dict[str, Any]:
        return {
            "channel_name": channel.name if channel else "",
            "language": channel.content_language if channel else "en",
            "format": "LONG",
        }


@dataclass(frozen=True)
class RunOutcome:
    run: AgentRun
    data: Any
    resume_at: datetime | None = None


def input_hash(code: str, data: dict[str, Any], prompt_version: str) -> str:
    canonical = json.dumps(
        {"agent": code, "input": data, "prompt": prompt_version}, sort_keys=True, default=str
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _today_usage(db: Session, code: str, now: datetime) -> tuple[int, int]:
    start = datetime.fromisoformat(limits.period_key("DAY", limits.PT, now)).replace(
        tzinfo=ZoneInfo(limits.PT)
    )
    row = db.execute(
        select(
            func.count(),
            func.coalesce(
                func.sum(func.coalesce(AgentRun.tokens_in, 0) + func.coalesce(AgentRun.tokens_out, 0)), 0
            ),
        ).where(AgentRun.agent_code == code, AgentRun.started_at >= start, AgentRun.status.in_(COUNTED))
    ).one()
    return int(row[0]), int(row[1])


def _finish(db: Session, run: AgentRun, status: str, **fields: Any) -> AgentRun:
    run.status = status
    run.finished_at = datetime.now(UTC)
    for k, v in fields.items():
        setattr(run, k, v)
    db.commit()
    return run


def run_agent(
    db: Session,
    gateway: Gateway,
    task: AgentTask,
    data: dict[str, Any],
    *,
    channel_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    job_id: str | None = None,
    idempotent: bool = True,
    now: datetime | None = None,
) -> RunOutcome:
    now = now or datetime.now(UTC)
    cfg = db.get_one(AgentConfiguration, task.code)
    parsed = task.input_model.model_validate(data)
    clean = parsed.model_dump(mode="json")
    digest = input_hash(task.code, clean, cfg.prompt_version)
    if idempotent:
        done = db.scalar(
            select(AgentRun)
            .where(
                AgentRun.agent_code == task.code,
                AgentRun.input_sha256 == digest,
                AgentRun.status.in_(("SUCCEEDED", "REPAIRED")),
            )
            .order_by(AgentRun.started_at.desc())
            .limit(1)
        )
        if done is not None:
            return RunOutcome(done, done.output)
    run = AgentRun(
        id=uuid7(),
        agent_code=task.code,
        channel_id=channel_id,
        project_id=project_id,
        job_id=job_id,
        input_sha256=digest,
        input=redact(clean),
        status="RUNNING",
        started_at=now,
    )
    db.add(run)
    db.flush()

    if not cfg.enabled:
        return RunOutcome(
            _finish(db, run, "ABORTED", error_class="DISABLED", error_detail="The agent is disabled."), None
        )
    stop = controls.stop_reason(db, agent_code=task.code, channel_id=channel_id)
    if stop is not None:
        return RunOutcome(
            _finish(db, run, "ABORTED", error_class=stop, error_detail="Stopped by the owner's controls."),
            None,
        )

    calls, tokens = _today_usage(db, task.code, now)
    calls -= 1  # this run is already counted as RUNNING
    budget_calls = cfg.limits.get("calls_per_day")
    budget_tokens = cfg.limits.get("tokens_per_day")
    if (budget_calls is not None and calls >= int(budget_calls)) or (
        budget_tokens is not None and tokens >= int(budget_tokens)
    ):
        resume = limits.next_reset("DAY", limits.PT, now)
        notify_owners(
            db,
            event_type="agent.limit",
            severity="WARNING",
            title="An agent reached its daily budget",
            body=f"{cfg.name} used its {budget_calls} runs for today. It continues after the reset "
            f"({resume:%H:%M} UTC), or raise its limit in the Agent Control Center.",
            dedup_key=f"agent.limit:{task.code}:{limits.period_key('DAY', limits.PT, now)}",
            dedup_window=timedelta(hours=24),
            link="/agents",
            now=now,
        )
        detail = f"Daily budget of {budget_calls} runs reached."
        return RunOutcome(
            _finish(db, run, "WAITING_QUOTA", error_class="AGENT_LIMIT", error_detail=detail), None, resume
        )
    db.commit()

    channel = db.get(Channel, channel_id) if channel_id else None
    system = render_system(task.code, cfg.name, cfg.prompt_version, task.context(parsed, channel))
    started = time.monotonic()
    try:
        result = gateway.text(
            db,
            task=task.task_type,
            messages=[Message("user", task.user_message(parsed))],
            system=system,
            schema=output_schema(task.code),
            channel_id=channel_id,
            agent_run_id=run.id,
            agent_code=task.code,
            prompt_version=cfg.prompt_version,
            max_output_tokens=task.max_output_tokens,
            temperature=task.temperature,
            chain=cfg.provider_chain or None,
            now=now,
        )
    except GatewayStoppedError as exc:
        return RunOutcome(_finish(db, run, "ABORTED", error_class="STOPPED", error_detail=str(exc)), None)
    except GatewayLimitError as exc:
        return RunOutcome(
            _finish(db, run, "WAITING_QUOTA", error_class="PROVIDER_LIMIT", error_detail=str(exc)[:500]),
            None,
            exc.resume_at,
        )
    except GatewayInvalidOutputError as exc:
        return RunOutcome(
            _finish(
                db,
                run,
                "FAILED",
                repair_attempted=True,
                error_class="VALIDATION",
                error_detail=str(exc)[:500],
            ),
            None,
        )
    except GatewayError as exc:
        return RunOutcome(
            _finish(db, run, "FAILED", error_class="UNAVAILABLE", error_detail=str(exc)[:500]), None
        )
    fields: dict[str, Any] = {
        "provider_code": result.provider_code,
        "model": result.provider_code.split(":", 1)[1],
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "repair_attempted": result.repaired,
        "output": redact(result.data),
    }
    if isinstance(result.data, dict) and "refusal" in result.data:
        reason = str(result.data["refusal"].get("reason", ""))
        notify_owners(
            db,
            event_type="agent.refused",
            severity="WARNING",
            title=f"{cfg.name} refused the task",
            body=reason[:300],
            dedup_key=f"agent.refused:{run.id}",
            link="/agents",
        )
        return RunOutcome(
            _finish(db, run, "FAILED", error_class="REFUSAL", error_detail=reason[:500], **fields), None
        )
    status = "REPAIRED" if result.repaired else "SUCCEEDED"
    return RunOutcome(_finish(db, run, status, **fields), result.data)
