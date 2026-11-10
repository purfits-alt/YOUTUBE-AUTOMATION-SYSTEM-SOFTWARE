"""Agent Control Center API (BACKEND_SPECIFICATION §4.16)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from tubeforge_agents.catalogue import BY_CODE
from tubeforge_agents.hello import HANDLERS
from tubeforge_agents.prompting import PROMPTS

from tubeforge.api.deps import Db, Principal, client_ip, request_id, require
from tubeforge.api.errors import ProblemError, not_found, problem_doc
from tubeforge.api.idempotency import Idempotency
from tubeforge.api.pagination import Cursor, Limit, Page, clamp_limit
from tubeforge.api.v1.channels import uuid_cursor
from tubeforge.audit import record
from tubeforge.db.models import AgentConfiguration, AgentRun, KillSwitch, ProviderRegistry
from tubeforge.queue import defer_in_transaction

router = APIRouter(tags=["agents"])
AgentsView = Annotated[Principal, Depends(require("agents.view"))]
AgentsManage = Annotated[Principal, Depends(require("agents.manage"))]
WRITE: dict[int | str, dict[str, Any]] = {
    409: problem_doc("AUDITOR_CANNOT_BE_DISABLED / NO_HANDLER / UNKNOWN_PROVIDER"),
    412: problem_doc("VERSION_CONFLICT: changed elsewhere (send the current ETag in If-Match)"),
    422: problem_doc("IDEMPOTENCY_MISMATCH"),
    428: problem_doc("IF_MATCH_REQUIRED"),
}
RunStatus = Literal["RUNNING", "SUCCEEDED", "FAILED", "REPAIRED", "ABORTED", "WAITING_QUOTA"]


class AgentLimits(BaseModel):
    calls_per_day: int | None = Field(default=None, ge=0, le=10_000)
    tokens_per_day: int | None = Field(default=None, ge=0, le=100_000_000)
    max_runtime_s: int | None = Field(default=None, ge=10, le=86_400)


class AgentStats(BaseModel):
    runs: int
    success_pct: int | None
    p50_ms: int | None
    tokens: int


class AgentOut(BaseModel):
    agent_code: str
    name: str
    kind: str
    is_auditor: bool
    enabled: bool
    paused: bool = Field(description="An AGENT kill switch is active.")
    runnable: bool = Field(description="A test run can be started from the Control Center.")
    version: str
    prompt_version: str
    provider_chain: list[str]
    limits: AgentLimits
    updated_at: datetime
    etag: str
    stats_24h: AgentStats


class AgentPatch(BaseModel):
    enabled: bool | None = None
    provider_chain: list[str] | None = Field(default=None, max_length=6)
    limits: AgentLimits | None = None


class AgentRunOut(BaseModel):
    id: uuid.UUID
    agent_code: str
    channel_id: uuid.UUID | None
    project_id: uuid.UUID | None
    status: RunStatus
    provider_code: str | None
    model: str | None
    tokens_in: int | None
    tokens_out: int | None
    duration_ms: int | None
    repair_attempted: bool
    error_class: str | None
    error_detail: str | None
    input: dict[str, Any]
    output: dict[str, Any] | None
    started_at: datetime
    finished_at: datetime | None


class TestRunIn(BaseModel):
    input: dict[str, Any] = Field(description="The agent's input, e.g. {'name': 'Ayesha'} for T00_HELLO.")


class QueuedOut(BaseModel):
    job_id: int | None
    agent_code: str


def _etag(cfg: AgentConfiguration) -> str:
    raw = json.dumps([cfg.enabled, cfg.provider_chain, cfg.limits, cfg.prompt_version], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _stats(db: Session, code: str, since: datetime) -> AgentStats:
    rows = db.execute(
        select(AgentRun.status, AgentRun.duration_ms, AgentRun.tokens_in, AgentRun.tokens_out).where(
            AgentRun.agent_code == code, AgentRun.started_at >= since
        )
    ).all()
    finished = [r for r in rows if r[0] in ("SUCCEEDED", "REPAIRED", "FAILED")]
    ok = [r for r in finished if r[0] in ("SUCCEEDED", "REPAIRED")]
    durations = [r[1] for r in ok if r[1] is not None]
    return AgentStats(
        runs=len(rows),
        success_pct=round(100 * len(ok) / len(finished)) if finished else None,
        p50_ms=int(median(durations)) if durations else None,
        tokens=sum((r[2] or 0) + (r[3] or 0) for r in rows),
    )


def _paused(db: Session) -> set[str]:
    return set(
        db.scalars(
            select(KillSwitch.target_id).where(KillSwitch.scope == "AGENT", KillSwitch.active.is_(True))
        )
    )


def _out(db: Session, cfg: AgentConfiguration, paused: set[str], since: datetime) -> AgentOut:
    info = BY_CODE.get(cfg.agent_code)
    return AgentOut(
        agent_code=cfg.agent_code,
        name=cfg.name,
        kind=info.kind if info else "UNKNOWN",
        is_auditor=cfg.is_auditor,
        enabled=cfg.enabled,
        paused=cfg.agent_code in paused,
        runnable=cfg.agent_code in HANDLERS,
        version=cfg.version,
        prompt_version=cfg.prompt_version,
        provider_chain=list(cfg.provider_chain or []),
        limits=AgentLimits(**{k: v for k, v in (cfg.limits or {}).items() if k in AgentLimits.model_fields}),
        updated_at=cfg.updated_at,
        etag=_etag(cfg),
        stats_24h=_stats(db, cfg.agent_code, since),
    )


def _agent(db: Session, code: str) -> AgentConfiguration:
    cfg = db.get(AgentConfiguration, code)
    if cfg is None:
        raise not_found("No such agent.")
    return cfg


@router.get("/agents", response_model=list[AgentOut])
def list_agents(db: Db, _: AgentsView) -> list[AgentOut]:
    since = datetime.now(UTC) - timedelta(hours=24)
    paused = _paused(db)
    rows = db.scalars(select(AgentConfiguration).order_by(AgentConfiguration.agent_code)).all()
    return [_out(db, cfg, paused, since) for cfg in rows]


@router.get("/agents/{code}", response_model=AgentOut)
def read_agent(code: str, db: Db, _: AgentsView, response: Response) -> AgentOut:
    cfg = _agent(db, code)
    out = _out(db, cfg, _paused(db), datetime.now(UTC) - timedelta(hours=24))
    response.headers["ETag"] = f'"{out.etag}"'
    return out


@router.patch("/agents/{code}", response_model=AgentOut, responses=WRITE)
def patch_agent(
    code: str,
    body: AgentPatch,
    request: Request,
    db: Db,
    p: AgentsManage,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> AgentOut:
    if not if_match:
        raise ProblemError(428, "IF_MATCH_REQUIRED", "Version needed", "Send the agent's ETag in If-Match.")
    cfg = db.get(AgentConfiguration, code, with_for_update=True)
    if cfg is None:
        raise not_found("No such agent.")
    if if_match.strip().strip('"') != _etag(cfg):
        raise ProblemError(412, "VERSION_CONFLICT", "Changed elsewhere", "Reload the agent and try again.")
    before = {"enabled": cfg.enabled, "provider_chain": cfg.provider_chain, "limits": cfg.limits}
    if body.enabled is False and cfg.is_auditor:
        raise ProblemError(
            409,
            "AUDITOR_CANNOT_BE_DISABLED",
            "Auditors stay on",
            "Pause an auditor with a kill switch and a reason instead.",
        )
    if body.enabled is not None:
        cfg.enabled = body.enabled
    if body.provider_chain is not None:
        known = {
            r.code: r
            for r in db.scalars(
                select(ProviderRegistry).where(ProviderRegistry.code.in_(body.provider_chain))
            )
        }
        unknown = [c for c in body.provider_chain if c not in known or known[c].capability != "LLM"]
        if unknown:
            raise ProblemError(
                409, "UNKNOWN_PROVIDER", "Unknown provider", f"Not text providers: {', '.join(unknown)}"
            )
        cfg.provider_chain = list(dict.fromkeys(body.provider_chain))
    if body.limits is not None:
        cfg.limits = {**(cfg.limits or {}), **body.limits.model_dump(exclude_unset=True)}
    cfg.updated_at = datetime.now(UTC)
    cfg.updated_by = p.user.id
    record(
        db,
        actor=p.actor,
        action="agent.config_changed",
        entity_type="agent",
        entity_id=code,
        before=before,
        after={"enabled": cfg.enabled, "provider_chain": cfg.provider_chain, "limits": cfg.limits},
        request_id=request_id(request),
        ip=client_ip(request),
    )
    db.commit()
    return _out(db, cfg, _paused(db), datetime.now(UTC) - timedelta(hours=24))


@router.get("/agents/{code}/prompts", response_model=list[str])
def prompt_versions(code: str, db: Db, _: AgentsView) -> list[str]:
    _agent(db, code)
    folder = PROMPTS / code
    return sorted(p.stem for p in folder.glob("v*.md")) if folder.is_dir() else []


@router.post("/agents/{code}/run", response_model=QueuedOut, status_code=202, responses=WRITE)
def test_run(code: str, body: TestRunIn, request: Request, db: Db, p: AgentsManage) -> Any:
    """Start a test run now (Agent Control Center). It goes through the queue, the agent's limits and
    the Gateway exactly like an orchestrated run."""
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    _agent(db, code)
    task = HANDLERS.get(code)
    if task is None:
        raise ProblemError(409, "NO_HANDLER", "Not runnable yet", "This agent arrives in a later phase.")
    try:
        task.input_model.model_validate(body.input)
    except ValueError as exc:
        raise ProblemError(400, "VALIDATION_ERROR", "Invalid input", str(exc)[:300]) from exc
    job = defer_in_transaction(
        db, "agent.run", queue="agents", args={"agent_code": code, "data": body.input, "idempotent": False}
    )
    record(
        db,
        actor=p.actor,
        action="agent.test_run",
        entity_type="agent",
        entity_id=code,
        request_id=request_id(request),
        ip=client_ip(request),
    )
    out = QueuedOut(job_id=job, agent_code=code)
    idem.store(202, out.model_dump(mode="json"))
    db.commit()
    return out


@router.get("/agent-runs", response_model=Page[AgentRunOut])
def list_runs(
    db: Db,
    _: AgentsView,
    limit: Limit = None,
    cursor: Cursor = None,
    agent: Annotated[str | None, Query(pattern=r"^[A-Z][A-Z0-9_]{2,40}$")] = None,
    status: RunStatus | None = None,
) -> Page[AgentRunOut]:
    n = clamp_limit(limit)
    stmt = select(AgentRun).order_by(AgentRun.id.desc())
    if agent:
        stmt = stmt.where(AgentRun.agent_code == agent)
    if status:
        stmt = stmt.where(AgentRun.status == status)
    after = uuid_cursor(cursor)
    if after is not None:
        stmt = stmt.where(AgentRun.id < after)
    rows = list(db.scalars(stmt.limit(n + 1)))
    more = len(rows) > n
    rows = rows[:n]
    return Page[AgentRunOut](
        items=[AgentRunOut.model_validate(r, from_attributes=True) for r in rows],
        next_cursor=f"c{rows[-1].id.int}" if more and rows else None,
    )


@router.get("/agent-runs/{run_id}", response_model=AgentRunOut)
def read_run(run_id: uuid.UUID, db: Db, _: AgentsView) -> AgentRunOut:
    row = db.get(AgentRun, run_id)
    if row is None:
        raise not_found("No such run.")
    return AgentRunOut.model_validate(row, from_attributes=True)
