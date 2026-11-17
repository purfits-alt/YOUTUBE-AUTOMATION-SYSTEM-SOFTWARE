"""Projects up to the script gate (BACKEND_SPECIFICATION §4.7, WORKFLOW_STATE_MACHINE §3).

States change only through commands, which call the orchestrator engine; its guards decide. The
facts the guards need (brief claims, contradicted claims, value-add fields, measured duration) are
read from the database here, never taken from the request. Model work (research, scripts, fact
checks) is queued for the workers in the same transaction as the state change.

Commands for later phases (cut review, fix paths) answer 409 ``NOT_AVAILABLE_YET``.
"""

# ruff: noqa: E501  (owner-facing messages read better unwrapped)
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from functools import cache
from typing import Annotated, Any, Literal, cast

import jsonschema_rs
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tubeforge.api.deps import Db, Principal, client_ip, request_id, require
from tubeforge.api.errors import ProblemError, not_found, problem_doc
from tubeforge.api.idempotency import Idempotency
from tubeforge.api.pagination import Limit, Page, clamp_limit
from tubeforge.api.v1.channels import get_channel, if_match, rejected, uuid_cursor
from tubeforge.api.v1.ideas import PackagingPromise, Text
from tubeforge.audit import Actor, record
from tubeforge.content import craft, scripts, value_add
from tubeforge.db.ids import uuid7
from tubeforge.db.models import (
    FactCheckClaim,
    OwnerValueAdd,
    ResearchBrief,
    Script,
    ScriptVersion,
    SourceDocument,
    VideoProject,
    WorkflowTransition,
)
from tubeforge.db.repository import VersionConflictError, update_versioned
from tubeforge.orchestrator import engine
from tubeforge.orchestrator.engine import TransitionRejected
from tubeforge.orchestrator.guards import GUARDS, GuardContext
from tubeforge.orchestrator.machines import MACHINES
from tubeforge.queue import defer_in_transaction

router = APIRouter(tags=["content"])
View = Annotated[Principal, Depends(require("content.view"))]
Edit = Annotated[Principal, Depends(require("content.edit"))]
Approve = Annotated[Principal, Depends(require("content.approve"))]
WRITE: dict[int | str, dict[str, Any]] = {
    409: problem_doc(
        "GUARD_FAILED / INVALID_TRANSITION / ACTOR_NOT_ALLOWED / EMERGENCY_STOP / NOT_AVAILABLE_YET / "
        "NOT_EDITABLE / NO_BRIEF / NO_SCRIPT / FACT_CHECK_PENDING / USE_IDEA_APPROVE"
    ),
    412: problem_doc("VERSION_CONFLICT: changed elsewhere"),
    422: problem_doc("SCRIPT_INVALID / VALIDATION_ERROR / IDEMPOTENCY_MISMATCH"),
}
ORCH = Actor("ORCH", "orchestrator")
Format = Literal["LONG", "SHORT"]
DEFAULT_DURATION_S = {"LONG": 480, "SHORT": 45}
EDITABLE_STATES = {"IDEA", "RESEARCHING", "RESEARCH_REVIEW", "SCRIPTING", "SCRIPT_REVIEW"}
SCRIPT_EDIT_STATES = {"SCRIPTING", "SCRIPT_REVIEW"}
Command = Literal[
    "start", "retry-research", "approve-research", "request-research-changes", "approve-script", "request-script-changes",
    "approve-cut", "request-cut-changes", "retry", "pause", "resume", "cancel", "choose-fix-path",
]  # fmt: skip
LATER = {"approve-cut", "request-cut-changes", "choose-fix-path"}
# Which command the owner can use in which state (the engine still decides).
COMMANDS_BY_STATE: dict[str, list[str]] = {
    "IDEA": ["start", "cancel"],
    "RESEARCHING": ["retry-research", "pause", "cancel"],
    "RESEARCH_REVIEW": ["approve-research", "request-research-changes", "pause", "cancel"],
    "SCRIPTING": ["pause", "cancel"],
    "SCRIPT_REVIEW": ["approve-script", "request-script-changes", "pause", "cancel"],
    "PAUSED": ["resume", "cancel"],
    "FAILED": ["retry", "cancel"],
}
# Work to queue when a project (re-)enters a state.
JOB_FOR_STATE = {"RESEARCHING": "content.research", "SCRIPTING": "content.script"}


# ------------------------------------------------------------------------------------- models
class GuardOut(BaseModel):
    code: str
    ok: bool
    message: str | None


class ProjectOut(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    idea_id: uuid.UUID | None
    parent_project_id: uuid.UUID | None
    format: Format
    state: str
    resume_to_state: str | None
    working_title: str
    packaging_promise: dict[str, Any] | None
    target_duration_s: int
    render_profile: dict[str, Any]
    locked_script_version_id: uuid.UUID | None
    originality_score: Decimal | None
    is_test: bool
    version: int
    created_at: datetime
    updated_at: datetime
    allowed_commands: list[str] = Field(default_factory=list)
    checks: list[GuardOut] = Field(
        default_factory=list, description="Guards of the next owner gate, from current data."
    )


class ProjectCreate(BaseModel):
    channel_id: uuid.UUID
    format: Format = "LONG"
    working_title: Annotated[Text, Field(min_length=5, max_length=100)]
    idea_id: uuid.UUID | None = None
    parent_project_id: uuid.UUID | None = None
    target_duration_s: int | None = Field(default=None, ge=10, le=3600)
    packaging_promise: PackagingPromise | None = None


class ProjectPatch(BaseModel):
    working_title: Annotated[Text, Field(min_length=5, max_length=100)] | None = None
    target_duration_s: int | None = Field(default=None, ge=10, le=3600)
    packaging_promise: PackagingPromise | None = None


class CommandIn(BaseModel):
    note: Annotated[Text, Field(max_length=1000)] | None = None
    override_reason: Annotated[Text, Field(max_length=1000)] | None = None


class CommandOut(BaseModel):
    project: ProjectOut
    transition_id: int | None
    job_ids: list[int] = Field(default_factory=list)


class TransitionOut(BaseModel):
    id: int
    from_state: str
    to_state: str
    event: str
    actor_type: str
    actor_id: str
    reason: str | None
    occurred_at: datetime


class ValueAddIn(BaseModel):
    own_opinion: Annotated[Text, Field(max_length=4000)] | None = None
    own_experience: Annotated[Text, Field(max_length=4000)] | None = None
    own_data: Annotated[Text, Field(max_length=4000)] | None = None
    own_examples: Annotated[Text, Field(max_length=4000)] | None = None
    owner_voice: Literal["NONE", "RECORDED", "CLONE"] = "NONE"
    owner_footage: bool = False
    owner_photos: bool = False


class ValueAddOut(ValueAddIn):
    score: Decimal
    filled_fields: list[str]
    min_chars: int = value_add.MIN_CHARS
    updated_at: datetime | None


class SourceRef(BaseModel):
    id: uuid.UUID
    url: str
    title: str | None


class BriefOut(BaseModel):
    id: uuid.UUID
    version: int
    status: Literal["DRAFT", "SUBMITTED", "APPROVED", "REJECTED"]
    content: dict[str, Any]
    created_at: datetime


class ClaimOut(BaseModel):
    id: uuid.UUID
    subject_type: Literal["RESEARCH_BRIEF", "SCRIPT_VERSION"]
    subject_id: uuid.UUID
    claim_text: str
    verdict: Literal["SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "OPINION"]
    explanation: str
    sources: list[SourceRef]
    owner_override_reason: str | None
    overridden_at: datetime | None


class OverrideIn(BaseModel):
    reason: Annotated[Text, Field(min_length=20, max_length=1000)]


class FindingOut(BaseModel):
    code: str
    severity: Literal["ERROR", "WARNING"]
    message: str


class VersionSummaryOut(BaseModel):
    id: uuid.UUID
    version: int
    author_type: Literal["AGENT", "OWNER"]
    author_id: str
    word_count: int
    est_duration_s: int
    content_sha256: str
    locked: bool
    fact_check: str
    created_at: datetime


class VersionOut(VersionSummaryOut):
    body: dict[str, Any]
    plain_text: str
    findings: list[FindingOut]
    hook_s: float


class ScriptVersionIn(BaseModel):
    body: dict[str, Any]
    based_on_version: int = Field(ge=1)


class DiffOut(BaseModel):
    a: int
    b: int
    lines: list[str]


class RegenerateIn(BaseModel):
    instruction: Annotated[Text, Field(min_length=5, max_length=800)]
    section: int | None = Field(default=None, ge=0, le=30)


class QueuedOut(BaseModel):
    job_id: int | None
    transition_id: int | None = None
    status: Literal["QUEUED"] = "QUEUED"


# ------------------------------------------------------------------------------------ helpers
def _project(db: Session, project_id: uuid.UUID, *, lock: bool = False) -> VideoProject:
    row = db.get(VideoProject, project_id, with_for_update=lock)
    if row is None or row.deleted_at is not None:
        raise not_found("No such project.")
    return row


def _audit(request: Request, db: Session, p: Principal, action: str, project: VideoProject, **d: Any) -> None:
    record(
        db,
        actor=p.actor,
        action=action,
        entity_type="video_project",
        entity_id=str(project.id),
        channel_id=project.channel_id,
        details=d or None,
        request_id=request_id(request),
        ip=client_ip(request),
    )


def _latest_brief(db: Session, project_id: uuid.UUID, *statuses: str) -> ResearchBrief | None:
    stmt = select(ResearchBrief).where(ResearchBrief.project_id == project_id)
    if statuses:
        stmt = stmt.where(ResearchBrief.status.in_(statuses))
    return db.scalar(stmt.order_by(ResearchBrief.version.desc()).limit(1))


def _script(db: Session, project_id: uuid.UUID) -> Script | None:
    return db.scalar(select(Script).where(Script.project_id == project_id))


def _latest_version(db: Session, project_id: uuid.UUID) -> ScriptVersion | None:
    script = _script(db, project_id)
    if script is None:
        return None
    return db.scalar(
        select(ScriptVersion)
        .where(ScriptVersion.script_id == script.id)
        .order_by(ScriptVersion.version.desc())
        .limit(1)
    )


def brief_facts(brief: ResearchBrief) -> list[dict[str, Any]]:
    from tubeforge_agents.content import brief_facts as facts

    return facts(brief)


def _contradicted(db: Session, version_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count()).where(
                FactCheckClaim.subject_type == "SCRIPT_VERSION",
                FactCheckClaim.subject_id == version_id,
                FactCheckClaim.verdict == "CONTRADICTED",
                FactCheckClaim.owner_override_reason.is_(None),
            )
        )
        or 0
    )


def _value_fields(db: Session, project_id: uuid.UUID) -> list[str]:
    row = db.get(OwnerValueAdd, project_id)
    return value_add.filled_fields(_value_dict(row)) if row else []


def _value_dict(row: OwnerValueAdd | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {k: getattr(row, k) for k in ValueAddIn.model_fields}


def _script_facts(db: Session, project: VideoProject, version: ScriptVersion) -> dict[str, Any]:
    return {
        "script_version_locked": True,
        "contradicted_claims": _contradicted(db, version.id),
        "value_add_fields": len(_value_fields(db, project.id)),
        "estimated_duration_s": version.est_duration_s,
    }


def _checks(db: Session, project: VideoProject) -> list[GuardOut]:
    """The next owner gate's guards, evaluated now (read-only)."""
    machine = MACHINES["video_project"]
    if project.state == "RESEARCH_REVIEW":
        brief = _latest_brief(db, project.id, "SUBMITTED", "APPROVED")
        payload: dict[str, Any] = {"claims": brief_facts(brief) if brief else []}
        event = "approve_research"
    elif project.state == "SCRIPT_REVIEW":
        version = _latest_version(db, project.id)
        if version is None:
            return [GuardOut(code="script", ok=False, message="No script yet.")]
        payload = _script_facts(db, project, version)
        event = "approve_script"
    else:
        return []
    edge = machine.edge(project.state, event)
    assert edge is not None
    ctx = GuardContext(
        db, machine, project, edge, "OWNER", payload, get_channel(db, project.channel_id), datetime.now(UTC)
    )
    out = []
    for name in edge.guards:
        if name == "script_locked":
            continue  # approving locks the latest version
        message = GUARDS[name](ctx)
        out.append(GuardOut(code=name, ok=message is None, message=message))
    return out


def project_out(db: Session, row: VideoProject) -> ProjectOut:
    data = {k: getattr(row, k) for k in ProjectOut.model_fields if hasattr(row, k)}
    commands = COMMANDS_BY_STATE.get(
        row.state, ["cancel"] if row.state not in ("ARCHIVED", "CANCELLED") else []
    )
    return ProjectOut(**data, allowed_commands=commands, checks=_checks(db, row))


def _queue(db: Session, state: str, project: VideoProject, instruction: str = "") -> list[int]:
    name = JOB_FOR_STATE.get(state)
    if name is None:
        return []
    args: dict[str, Any] = {"project_id": str(project.id)}
    if name == "content.script" and instruction:
        args["instruction"] = instruction
    job = defer_in_transaction(db, name, queue="agents", args=args)
    return [job] if job is not None else []


@cache
def _script_validator() -> Any:
    from tubeforge_agents.prompting import PROMPTS

    schema = json.loads((PROMPTS / "A11_SCRIPTWRITING" / "schema.json").read_text(encoding="utf-8"))
    return jsonschema_rs.validator_for(schema)


def _findings(project: VideoProject, body: dict[str, Any], db: Session) -> list[craft.Finding]:
    brief = _latest_brief(db, project.id, "APPROVED")
    ids = {str(c.get("id")) for c in brief.content.get("claims", [])} if brief else None
    return craft.check_script(
        body,
        fmt=cast(craft.Format, project.format),
        target_duration_s=project.target_duration_s,
        claim_ids=ids,
    )


def _summary(v: ScriptVersion) -> dict[str, Any]:
    return {
        "id": v.id,
        "version": v.version,
        "author_type": v.author_type,
        "author_id": v.author_id,
        "word_count": v.word_count,
        "est_duration_s": v.est_duration_s,
        "content_sha256": v.content_sha256,
        "locked": v.locked,
        "fact_check": str(v.body.get("_fact_check", "PENDING")),
        "created_at": v.created_at,
    }


def _version_out(db: Session, project: VideoProject, v: ScriptVersion) -> VersionOut:
    body = scripts.content(v.body)
    hook = str(body.get("hook", {}).get("text", ""))
    return VersionOut(
        **_summary(v),
        body=body,
        plain_text=v.plain_text,
        findings=[
            FindingOut(code=f.code, severity=f.severity, message=f.message)
            for f in _findings(project, body, db)
        ],
        hook_s=craft.seconds(craft.words(hook)),
    )


# ------------------------------------------------------------------------------------ projects
@router.get("/projects", response_model=Page[ProjectOut])
def list_projects(
    db: Db,
    p: View,
    channel_id: uuid.UUID | None = None,
    state: str | None = Query(default=None, max_length=30),
    format: Format | None = None,
    include_tests: bool = False,
    limit: Limit = None,
    cursor: Annotated[str | None, Query(pattern=r"^c[0-9]{1,40}$")] = None,
) -> Page[ProjectOut]:
    n = clamp_limit(limit)
    stmt = select(VideoProject).where(VideoProject.deleted_at.is_(None)).order_by(VideoProject.id.desc())
    if channel_id:
        stmt = stmt.where(VideoProject.channel_id == channel_id)
    if state:
        stmt = stmt.where(VideoProject.state == state)
    if format:
        stmt = stmt.where(VideoProject.format == format)
    if not include_tests:
        stmt = stmt.where(VideoProject.is_test.is_(False))
    after = uuid_cursor(cursor)
    if after is not None:
        stmt = stmt.where(VideoProject.id < after)
    rows = list(db.scalars(stmt.limit(n + 1)))
    more = len(rows) > n
    rows = rows[:n]
    return Page[ProjectOut](
        items=[project_out(db, r) for r in rows], next_cursor=f"c{rows[-1].id.int}" if more and rows else None
    )


@router.post("/projects", response_model=ProjectOut, status_code=201, responses=WRITE)
def create_project(body: ProjectCreate, request: Request, db: Db, p: Edit) -> Any:
    """A project without an idea (the owner's own topic). Projects from ideas are made by approving
    the idea (``POST /ideas/{id}/commands/approve``)."""
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    get_channel(db, body.channel_id)
    if body.idea_id is not None:
        raise ProblemError(
            409, "USE_IDEA_APPROVE", "Approve the idea", "Approve the idea to start its project."
        )
    if body.parent_project_id is not None:
        parent = _project(db, body.parent_project_id)
        if parent.channel_id != body.channel_id:
            raise not_found("No such parent project on this channel.")
    row = VideoProject(
        id=uuid7(),
        channel_id=body.channel_id,
        parent_project_id=body.parent_project_id,
        format=body.format,
        state="IDEA",
        working_title=body.working_title.strip(),
        packaging_promise=body.packaging_promise.model_dump() if body.packaging_promise else None,
        target_duration_s=body.target_duration_s or DEFAULT_DURATION_S[body.format],
        render_profile={"profile": "LONG_1080" if body.format == "LONG" else "SHORT_1080"},
    )
    db.add(row)
    db.flush()
    db.add(OwnerValueAdd(project_id=row.id))
    db.flush()
    db.refresh(row)
    _audit(request, db, p, "project.created", row, title=row.working_title)
    out = project_out(db, row)
    idem.store(201, out.model_dump(mode="json"))
    db.commit()
    return out


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, db: Db, p: View, response: Response) -> ProjectOut:
    row = _project(db, project_id)
    response.headers["ETag"] = f'"{row.version}"'
    return project_out(db, row)


@router.patch("/projects/{project_id}", response_model=ProjectOut, responses=WRITE)
def edit_project(
    project_id: uuid.UUID,
    body: ProjectPatch,
    request: Request,
    db: Db,
    p: Edit,
    if_match_header: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ProjectOut:
    expected = if_match(if_match_header)
    row = _project(db, project_id)
    if row.state not in EDITABLE_STATES:
        raise ProblemError(
            409, "NOT_EDITABLE", "Not editable", f"A project that is {row.state} cannot be edited here."
        )
    values = body.model_dump(exclude_unset=True, mode="json")
    if not values:
        return project_out(db, row)
    if "working_title" in values:
        values["working_title"] = str(values["working_title"]).strip()
    try:
        update_versioned(db, VideoProject, project_id, expected, values)
    except VersionConflictError as exc:
        raise ProblemError(
            412, "VERSION_CONFLICT", "Changed elsewhere", "Reload and try again.", current_version=exc.current
        ) from exc
    db.refresh(row)
    _audit(request, db, p, "project.edited", row, fields=sorted(values))
    db.commit()
    return project_out(db, row)


@router.post("/projects/{project_id}/commands/{cmd}", response_model=CommandOut, responses=WRITE)
def project_command(
    project_id: uuid.UUID,
    cmd: Command,
    request: Request,
    response: Response,
    db: Db,
    p: Edit,
    body: CommandIn | None = None,
) -> Any:
    """``approve-*`` need ``content.approve``; ``cancel`` needs ``project.cancel``."""
    body = body or CommandIn()
    if cmd.startswith("approve-") and not p.has("content.approve"):
        raise ProblemError(403, "FORBIDDEN", "Not allowed", "You may not approve this gate.")
    if cmd == "cancel" and not p.has("project.cancel"):
        raise ProblemError(403, "FORBIDDEN", "Not allowed", "You may not cancel projects.")
    if cmd in LATER:
        raise ProblemError(
            409, "NOT_AVAILABLE_YET", "Coming later", "This step arrives with video assembly (Phase 9)."
        )
    idem = Idempotency(db, request, p.user.id, {"cmd": cmd, **body.model_dump(mode="json")})
    if (replayed := idem.replay()) is not None:
        return replayed
    project = _project(db, project_id, lock=True)
    if cmd == "retry-research":
        # Research found too little or was refused: run it again (optionally with the owner's extra
        # search words). No state change: the project stays in RESEARCHING.
        if project.state != "RESEARCHING":
            raise ProblemError(
                409,
                "INVALID_TRANSITION",
                "Not now",
                "Research can be run again while the project is researching.",
            )
        extra = [w.strip() for w in (body.note or "").replace("\n", ",").split(",") if w.strip()][:5]
        job = defer_in_transaction(
            db,
            "content.research",
            queue="agents",
            args={"project_id": str(project.id), "extra_queries": extra},
        )
        _audit(request, db, p, "project.retry-research", project, extra_queries=extra)
        out = CommandOut(project=project_out(db, project), transition_id=None, job_ids=[job] if job else [])
        response.status_code = 202
        idem.store(202, out.model_dump(mode="json"))
        db.commit()
        return out
    machine = MACHINES["video_project"]
    actor: Actor = p.actor
    payload: dict[str, Any] = {}
    if body.override_reason:
        payload["override_reason"] = body.override_reason
    instruction = ""
    brief: ResearchBrief | None = None
    version: ScriptVersion | None = None
    if cmd == "start":
        event, actor = "start_research", ORCH  # the orchestrator starts research on the owner's request
    elif cmd == "approve-research":
        brief = _latest_brief(db, project.id, "SUBMITTED")
        if brief is None:
            raise ProblemError(409, "NO_BRIEF", "No brief", "There is no research brief waiting for review.")
        event, payload["claims"] = "approve_research", brief_facts(brief)
    elif cmd == "request-research-changes":
        brief = _latest_brief(db, project.id, "SUBMITTED")
        event = "request_changes"
    elif cmd == "approve-script":
        version = _latest_version(db, project.id)
        if version is None:
            raise ProblemError(409, "NO_SCRIPT", "No script", "There is no script to approve yet.")
        if version.body.get("_fact_check") not in ("DONE", "NO_SOURCES"):
            raise ProblemError(
                409,
                "FACT_CHECK_PENDING",
                "Still checking",
                "The latest version is still being fact-checked. Try again in a minute.",
            )
        event = "approve_script"
        payload.update(_script_facts(db, project, version))
    elif cmd == "request-script-changes":
        event, instruction = "request_changes", (body.note or "")
    else:
        event = cmd  # pause, resume, cancel, retry (universal events)
    try:
        result = engine.transition(
            db,
            machine,
            project.id,
            event,
            actor=actor,
            payload=payload,
            reason=body.note or body.override_reason,
        )
    except TransitionRejected as exc:
        db.rollback()
        raise rejected(exc) from exc
    if brief is not None:
        brief.status = "APPROVED" if cmd == "approve-research" else "REJECTED"
    if version is not None:
        version.locked = True
        project.locked_script_version_id = version.id
    db.flush()
    db.refresh(project)
    jobs: list[int] = []
    if result.from_state != result.to_state and cmd != "pause":
        jobs = _queue(db, project.state, project, instruction)
    _audit(request, db, p, f"project.{cmd}", project, from_state=result.from_state, to_state=result.to_state)
    out = CommandOut(project=project_out(db, project), transition_id=result.transition_id, job_ids=jobs)
    status = 202 if jobs else 200
    response.status_code = status
    idem.store(status, out.model_dump(mode="json"))
    db.commit()
    return out


@router.get("/projects/{project_id}/timeline-history", response_model=list[TransitionOut])
def timeline_history(project_id: uuid.UUID, db: Db, p: View) -> list[TransitionOut]:
    _project(db, project_id)
    rows = db.scalars(
        select(WorkflowTransition)
        .where(WorkflowTransition.entity_type == "video_project", WorkflowTransition.entity_id == project_id)
        .order_by(WorkflowTransition.id)
    )
    return [TransitionOut.model_validate(r, from_attributes=True) for r in rows]


# ----------------------------------------------------------------------------------- value add
def _value_out(row: OwnerValueAdd | None) -> ValueAddOut:
    values = _value_dict(row)
    return ValueAddOut(
        **{k: v for k, v in values.items() if v is not None},
        score=value_add.score(values),
        filled_fields=value_add.filled_fields(values),
        updated_at=row.updated_at if row else None,
    )


@router.get("/projects/{project_id}/value-add", response_model=ValueAddOut)
def get_value_add(project_id: uuid.UUID, db: Db, p: View) -> ValueAddOut:
    _project(db, project_id)
    return _value_out(db.get(OwnerValueAdd, project_id))


@router.put("/projects/{project_id}/value-add", response_model=ValueAddOut, responses=WRITE)
def put_value_add(project_id: uuid.UUID, body: ValueAddIn, request: Request, db: Db, p: Edit) -> ValueAddOut:
    project = _project(db, project_id)
    row = db.get(OwnerValueAdd, project_id, with_for_update=True)
    if row is None:
        row = OwnerValueAdd(project_id=project_id)
        db.add(row)
    for k, v in body.model_dump().items():
        setattr(
            row, k, v.strip() if isinstance(v, str) and v.strip() else (None if isinstance(v, str) else v)
        )
    row.score = value_add.score(_value_dict(row))
    row.updated_at = datetime.now(UTC)
    _audit(request, db, p, "project.value_add_saved", project, score=str(row.score))
    db.commit()
    return _value_out(row)


# ----------------------------------------------------------------------------- research, claims
def _brief_out(row: ResearchBrief) -> BriefOut:
    return BriefOut(
        id=row.id, version=row.version, status=row.status, content=row.content, created_at=row.created_at
    )


@router.get("/projects/{project_id}/research", response_model=list[BriefOut])
def list_briefs(project_id: uuid.UUID, db: Db, p: View) -> list[BriefOut]:
    _project(db, project_id)
    rows = db.scalars(
        select(ResearchBrief)
        .where(ResearchBrief.project_id == project_id)
        .order_by(ResearchBrief.version.desc())
    )
    return [_brief_out(r) for r in rows]


@router.get("/projects/{project_id}/research/{version}", response_model=BriefOut)
def get_brief(project_id: uuid.UUID, version: int, db: Db, p: View) -> BriefOut:
    _project(db, project_id)
    row = db.scalar(
        select(ResearchBrief).where(ResearchBrief.project_id == project_id, ResearchBrief.version == version)
    )
    if row is None:
        raise not_found("No such research brief version.")
    return _brief_out(row)


def _claim_out(db: Session, c: FactCheckClaim) -> ClaimOut:
    docs = (
        db.scalars(select(SourceDocument).where(SourceDocument.id.in_(c.source_document_ids))).all()
        if c.source_document_ids
        else []
    )
    return ClaimOut(
        id=c.id, subject_type=c.subject_type, subject_id=c.subject_id, claim_text=c.claim_text,
        verdict=c.verdict, explanation=c.explanation, owner_override_reason=c.owner_override_reason,
        overridden_at=c.overridden_at, sources=[SourceRef(id=d.id, url=d.url, title=d.title) for d in docs],
    )  # fmt: skip


@router.get("/projects/{project_id}/claims", response_model=list[ClaimOut])
def list_claims(
    project_id: uuid.UUID,
    db: Db,
    p: View,
    subject: Literal["RESEARCH_BRIEF", "SCRIPT_VERSION"] | None = None,
    subject_id: uuid.UUID | None = None,
) -> list[ClaimOut]:
    _project(db, project_id)
    stmt = select(FactCheckClaim).where(FactCheckClaim.project_id == project_id)
    if subject:
        stmt = stmt.where(FactCheckClaim.subject_type == subject)
    if subject_id:
        stmt = stmt.where(FactCheckClaim.subject_id == subject_id)
    return [_claim_out(db, c) for c in db.scalars(stmt.order_by(FactCheckClaim.id))]


@router.post("/claims/{claim_id}/override", response_model=ClaimOut, responses=WRITE)
def override_claim(claim_id: uuid.UUID, body: OverrideIn, request: Request, db: Db, p: Approve) -> Any:
    """The owner accepts a contradicted or unsupported claim with a written reason (≥ 20 characters)."""
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    claim = db.get(FactCheckClaim, claim_id, with_for_update=True)
    if claim is None:
        raise not_found("No such claim.")
    project = _project(db, claim.project_id)
    claim.owner_override_reason = body.reason.strip()
    claim.overridden_by = p.user.id
    claim.overridden_at = datetime.now(UTC)
    if claim.subject_type == "RESEARCH_BRIEF":
        brief = db.get(ResearchBrief, claim.subject_id, with_for_update=True)
        prefix = claim.claim_text.split(":", 1)[0].strip()
        if brief is not None:
            brief.content = {
                **brief.content,
                "claims": [
                    {**c, "override_reason": claim.owner_override_reason} if str(c.get("id")) == prefix else c
                    for c in brief.content.get("claims", [])
                ],
            }
    _audit(request, db, p, "claim.overridden", project, claim_id=str(claim.id), verdict=claim.verdict)
    out = _claim_out(db, claim)
    idem.store(200, out.model_dump(mode="json"))
    db.commit()
    return out


# ------------------------------------------------------------------------------------- scripts
def _versions(db: Session, project_id: uuid.UUID) -> list[ScriptVersion]:
    script = _script(db, project_id)
    if script is None:
        return []
    return list(
        db.scalars(
            select(ScriptVersion)
            .where(ScriptVersion.script_id == script.id)
            .order_by(ScriptVersion.version.desc())
        )
    )


def _version(db: Session, project_id: uuid.UUID, number: int) -> ScriptVersion:
    found = next((v for v in _versions(db, project_id) if v.version == number), None)
    if found is None:
        raise not_found("No such script version.")
    return found


@router.get("/projects/{project_id}/script/versions", response_model=list[VersionSummaryOut])
def list_versions(project_id: uuid.UUID, db: Db, p: View) -> list[VersionSummaryOut]:
    _project(db, project_id)
    return [VersionSummaryOut(**_summary(v)) for v in _versions(db, project_id)]


@router.get("/projects/{project_id}/script/versions/{number}", response_model=VersionOut)
def get_version(project_id: uuid.UUID, number: int, db: Db, p: View) -> VersionOut:
    project = _project(db, project_id)
    return _version_out(db, project, _version(db, project_id, number))


@router.get("/projects/{project_id}/script/diff", response_model=DiffOut)
def diff_versions(project_id: uuid.UUID, a: int, b: int, db: Db, p: View) -> DiffOut:
    _project(db, project_id)
    va, vb = _version(db, project_id, a), _version(db, project_id, b)
    return DiffOut(
        a=a, b=b, lines=scripts.diff(scripts.content(va.body), scripts.content(vb.body), f"v{a}", f"v{b}")
    )


@router.post(
    "/projects/{project_id}/script/versions", response_model=VersionOut, status_code=201, responses=WRITE
)
def save_version(project_id: uuid.UUID, body: ScriptVersionIn, request: Request, db: Db, p: Edit) -> Any:
    """The owner's edit becomes a new version. Craft findings are returned, not enforced; the new
    text is fact-checked by a queued job before the script can be approved."""
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    project = _project(db, project_id, lock=True)
    if project.state not in SCRIPT_EDIT_STATES:
        raise ProblemError(
            409,
            "NOT_EDITABLE",
            "Not editable",
            f"The script cannot be edited while the project is {project.state}.",
        )
    script = _script(db, project_id)
    latest = _latest_version(db, project_id)
    if script is None or latest is None:
        raise ProblemError(409, "NO_SCRIPT", "No script", "Wait for the first draft before editing.")
    if body.based_on_version != latest.version:
        raise ProblemError(
            412,
            "VERSION_CONFLICT",
            "Changed elsewhere",
            f"Version {latest.version} is the latest; reload it first.",
            current_version=latest.version,
        )
    content = scripts.content(body.body)
    errors = [f"{e.instance_path or '/'}: {e.message}" for e in _script_validator().iter_errors(content)]
    if errors:
        raise ProblemError(422, "SCRIPT_INVALID", "Script not valid", "; ".join(errors[:5]))
    words, est = craft.measure(content)
    content = {**content, "word_count": words, "est_duration_s": est}
    info = scripts.summary(content)
    if info["content_sha256"] == latest.content_sha256:
        out = _version_out(db, project, latest)
        idem.store(201, out.model_dump(mode="json"))
        db.commit()
        return out
    version = ScriptVersion(
        id=uuid7(), script_id=script.id, version=latest.version + 1, author_type="OWNER", author_id=str(p.user.id),
        body={**content, "_fact_check": "PENDING"}, plain_text=info["plain_text"], word_count=info["word_count"],
        est_duration_s=info["est_duration_s"], content_sha256=info["content_sha256"],
    )  # fmt: skip
    db.add(version)
    db.flush()
    defer_in_transaction(db, "content.fact_check", queue="agents", args={"version_id": str(version.id)})
    db.refresh(version)
    _audit(request, db, p, "script.version_saved", project, version=version.version)
    out = _version_out(db, project, version)
    idem.store(201, out.model_dump(mode="json"))
    db.commit()
    return out


@router.post(
    "/projects/{project_id}/script/regenerate", response_model=QueuedOut, status_code=202, responses=WRITE
)
def regenerate(project_id: uuid.UUID, body: RegenerateIn, request: Request, db: Db, p: Edit) -> Any:
    """A new draft with the owner's instruction. From SCRIPT_REVIEW the project goes back to SCRIPTING."""
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    project = _project(db, project_id, lock=True)
    if project.state != "SCRIPT_REVIEW":
        raise ProblemError(
            409, "NOT_EDITABLE", "Not now", "A new draft can be asked for while the script is in review."
        )
    instruction = body.instruction.strip()
    if body.section is not None:
        instruction = f"Rewrite section {body.section} (0-based) as follows and keep the rest close to the current draft: {instruction}"
    try:
        result = engine.transition(
            db,
            MACHINES["video_project"],
            project.id,
            "request_changes",
            actor=p.actor,
            reason=instruction[:300],
        )
    except TransitionRejected as exc:
        db.rollback()
        raise rejected(exc) from exc
    jobs = _queue(db, "SCRIPTING", project, instruction)
    _audit(request, db, p, "script.regenerate_requested", project, section=body.section)
    out = QueuedOut(job_id=jobs[0] if jobs else None, transition_id=result.transition_id)
    idem.store(202, out.model_dump(mode="json"))
    db.commit()
    return out
