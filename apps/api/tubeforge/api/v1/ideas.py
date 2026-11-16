"""Ideas, content calendar and Replicate (BACKEND_SPECIFICATION §4.6, US-4.6, ADR-0025).

Generating ideas and variations queues worker jobs (A08 never runs in the API). Owner ideas are
checked here: forbidden phrases are refused and similarity to earlier ideas is stored, so the
``idea_original`` guard can ask for a reason before a near-duplicate is approved. Approving an idea
creates its project and queues the research job in the same transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from datetime import date as Day  # noqa: N812 - a field is named "date"
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.api.deps import Db, Principal, client_ip, request_id, require
from tubeforge.api.errors import ProblemError, not_found, problem_doc
from tubeforge.api.idempotency import Idempotency
from tubeforge.api.pagination import Limit, Page, clamp_limit
from tubeforge.api.v1.channels import get_channel, if_match, rejected, uuid_cursor
from tubeforge.audit import record
from tubeforge.content.ideas import closest_idea, similarity_flags
from tubeforge.db.ids import uuid7
from tubeforge.db.models import TrendItem, VideoIdea, VideoProject
from tubeforge.db.repository import VersionConflictError, update_versioned
from tubeforge.orchestrator import engine
from tubeforge.orchestrator.controls import stop_reason
from tubeforge.orchestrator.engine import TransitionRejected
from tubeforge.orchestrator.machines import MACHINES
from tubeforge.queue import defer_in_transaction
from tubeforge.research.forbidden import scan

router = APIRouter(tags=["content"])
View = Annotated[Principal, Depends(require("content.view"))]
Edit = Annotated[Principal, Depends(require("content.edit"))]
WRITE: dict[int | str, dict[str, Any]] = {
    409: problem_doc("GUARD_FAILED / INVALID_TRANSITION / EMERGENCY_STOP / STOPPED / NOT_EDITABLE"),
    412: problem_doc("VERSION_CONFLICT: changed elsewhere (send the current version in If-Match)"),
    422: problem_doc("FORBIDDEN_PHRASE / IDEMPOTENCY_MISMATCH"),
}
IdeaState = Literal[
    "SUGGESTED", "SHORTLISTED", "SCHEDULED", "APPROVED", "IN_PRODUCTION", "PRODUCED", "DISCARDED"
]
Format = Literal["LONG", "SHORT"]
VariationKind = Literal["PART_2", "NEW_ANGLE", "UPDATE", "SHORT_FROM_LONG", "LONG_FROM_SHORT", "SERIES"]
Text = Annotated[str, Field(pattern=r"^[^\x00-\x08\x0b\x0c\x0e-\x1f]*$")]
EDITABLE = {"SUGGESTED", "SHORTLISTED", "SCHEDULED"}
WideCursor = Annotated[str | None, Query(pattern=r"^c[0-9]{1,40}$")]


class PackagingPromise(BaseModel):
    title_idea: Annotated[Text, Field(min_length=5, max_length=100)]
    thumbnail_text_idea: Annotated[Text, Field(min_length=1, max_length=40)]
    promise_statement: Annotated[Text, Field(min_length=10, max_length=200)]


class IdeaIn(BaseModel):
    title: Annotated[Text, Field(min_length=5, max_length=100)]
    angle: Annotated[Text, Field(min_length=5, max_length=500)]
    format: Format = "LONG"
    target_viewer: Annotated[Text, Field(max_length=200)] | None = None
    pillar: Annotated[Text, Field(max_length=60)] | None = None
    packaging_promise: PackagingPromise | None = None
    owner_value_add_prompt: Annotated[Text, Field(max_length=200)] | None = None


class IdeaOut(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    state: IdeaState
    title: str
    angle: str
    target_viewer: str | None
    format: Format
    pillar: str | None
    trend_item_id: uuid.UUID | None
    originality_notes: str | None
    similarity_max: Decimal | None
    similar_to_id: uuid.UUID | None
    similar_to_title: str | None
    duplicate: bool = Field(description="At or above the duplicate limit: approval needs a written reason.")
    maybe_same_idea: bool = Field(description="Paraphrase band: maybe the same idea in other words.")
    calendar_date: date | None
    expires_at: datetime | None
    source: Literal["AGENT", "OWNER", "BLUEPRINT", "REPLICATE"]
    based_on_youtube_video_id: str | None
    variation_kind: VariationKind | None
    similarity_to_source: Decimal | None
    packaging_promise: dict[str, Any] | None
    owner_value_add_prompt: str | None
    project_id: uuid.UUID | None
    version: int
    created_at: datetime
    updated_at: datetime


class GenerateIn(BaseModel):
    count: int = Field(default=10, ge=1, le=20)
    format: Format | None = None
    pillar: Annotated[Text, Field(max_length=60)] | None = None


class QueuedOut(BaseModel):
    job_id: int | None
    status: Literal["QUEUED"] = "QUEUED"


class CommandIn(BaseModel):
    date: Day | None = None
    override_reason: Annotated[Text, Field(max_length=1000)] | None = None
    target_duration_s: int | None = Field(default=None, ge=10, le=3600)


class CommandOut(BaseModel):
    idea: IdeaOut
    transition_id: int | None
    project_id: uuid.UUID | None = None
    job_ids: list[int] = Field(default_factory=list)


class CalendarItemOut(BaseModel):
    id: uuid.UUID
    date: Day
    channel_id: uuid.UUID
    title: str
    format: Format
    state: IdeaState
    project_id: uuid.UUID | None
    project_state: str | None


class CalendarOut(BaseModel):
    items: list[CalendarItemOut]


class DateIn(BaseModel):
    date: Day


class WinnerOut(BaseModel):
    """One of the channel's own published videos. Analytics fields arrive with Phase 13."""

    youtube_video_id: str
    title: str
    project_id: uuid.UUID
    published_at: datetime | None = None
    views: int | None = None
    multiple: float | None = None


class ReplicateOut(BaseModel):
    winners: list[WinnerOut]
    variations: list[IdeaOut]


class ReplicateIn(BaseModel):
    youtube_video_id: Annotated[str, Field(min_length=6, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")]
    kind: VariationKind
    note: Annotated[Text, Field(max_length=500)] | None = None
    count: int = Field(default=5, ge=1, le=10)


# ----------------------------------------------------------------------------------- helpers
def _audit(request: Request, db: Session, p: Principal, action: str, idea: VideoIdea, **d: Any) -> None:
    record(
        db,
        actor=p.actor,
        action=action,
        entity_type="video_idea",
        entity_id=str(idea.id),
        channel_id=idea.channel_id,
        details=d or None,
        request_id=request_id(request),
        ip=client_ip(request),
    )


def _project_of(db: Session, idea_id: uuid.UUID) -> VideoProject | None:
    return db.scalar(
        select(VideoProject)
        .where(VideoProject.idea_id == idea_id, VideoProject.deleted_at.is_(None))
        .limit(1)
    )


def idea_out(db: Session, row: VideoIdea) -> IdeaOut:
    duplicate, paraphrase = similarity_flags(row.similarity_max)
    similar = db.get(VideoIdea, row.similar_to_id) if row.similar_to_id else None
    project = _project_of(db, row.id)
    return IdeaOut(
        **{k: getattr(row, k) for k in IdeaOut.model_fields if hasattr(row, k)},
        similar_to_title=similar.title if similar else None,
        duplicate=duplicate,
        maybe_same_idea=paraphrase,
        project_id=project.id if project else None,
    )


def _idea(db: Session, idea_id: uuid.UUID, *, lock: bool = False) -> VideoIdea:
    row = db.get(VideoIdea, idea_id, with_for_update=lock)
    if row is None or row.deleted_at is not None:
        raise not_found("No such idea.")
    return row


def _no_promises(body: BaseModel) -> None:
    hits = scan(body.model_dump(mode="json"))
    if hits:
        raise ProblemError(
            422,
            "FORBIDDEN_PHRASE",
            "Not allowed",
            f"“{hits[0].phrase}” makes a promise TubeForge cannot keep. Please reword it.",
        )


def _not_stopped(db: Session, channel_id: uuid.UUID) -> None:
    if stop_reason(db, channel_id=channel_id) is not None:
        raise ProblemError(
            409, "STOPPED", "Stopped", "Emergency Stop or a kill switch is on for this channel."
        )


# -------------------------------------------------------------------------------------- ideas
@router.get("/channels/{channel_id}/ideas", response_model=Page[IdeaOut])
def list_ideas(
    channel_id: uuid.UUID,
    db: Db,
    p: View,
    state: IdeaState | None = None,
    format: Format | None = None,
    pillar: str | None = None,
    source: Literal["AGENT", "OWNER", "BLUEPRINT", "REPLICATE"] | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Limit = None,
    cursor: WideCursor = None,
) -> Page[IdeaOut]:
    get_channel(db, channel_id)
    n = clamp_limit(limit)
    stmt = (
        select(VideoIdea)
        .where(VideoIdea.channel_id == channel_id, VideoIdea.deleted_at.is_(None))
        .order_by(VideoIdea.id.desc())
    )
    if state:
        stmt = stmt.where(VideoIdea.state == state)
    if format:
        stmt = stmt.where(VideoIdea.format == format)
    if pillar:
        stmt = stmt.where(VideoIdea.pillar == pillar)
    if source:
        stmt = stmt.where(VideoIdea.source == source)
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(VideoIdea.title.ilike(like) | VideoIdea.angle.ilike(like))
    after = uuid_cursor(cursor)
    if after is not None:
        stmt = stmt.where(VideoIdea.id < after)
    rows = list(db.scalars(stmt.limit(n + 1)))
    more = len(rows) > n
    rows = rows[:n]
    return Page[IdeaOut](
        items=[idea_out(db, r) for r in rows],
        next_cursor=f"c{rows[-1].id.int}" if more and rows else None,
    )


@router.get("/ideas/{idea_id}", response_model=IdeaOut)
def get_idea(idea_id: uuid.UUID, db: Db, p: View, response: Response) -> IdeaOut:
    row = _idea(db, idea_id)
    response.headers["ETag"] = f'"{row.version}"'
    return idea_out(db, row)


@router.post("/channels/{channel_id}/ideas", response_model=IdeaOut, status_code=201, responses=WRITE)
def create_idea(channel_id: uuid.UUID, body: IdeaIn, request: Request, db: Db, p: Edit) -> Any:
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    get_channel(db, channel_id)
    _no_promises(body)
    near = closest_idea(db, channel_id, body.title)
    row = VideoIdea(
        id=uuid7(),
        channel_id=channel_id,
        state="SUGGESTED",
        title=body.title.strip(),
        angle=body.angle.strip(),
        target_viewer=body.target_viewer,
        format=body.format,
        pillar=body.pillar,
        source="OWNER",
        similarity_max=near.score,
        similar_to_id=near.idea_id,
        packaging_promise=body.packaging_promise.model_dump() if body.packaging_promise else None,
        owner_value_add_prompt=body.owner_value_add_prompt,
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    _audit(request, db, p, "idea.created", row, title=row.title)
    out = idea_out(db, row)
    idem.store(201, out.model_dump(mode="json"))
    db.commit()
    return out


@router.post(
    "/channels/{channel_id}/ideas/generate", response_model=QueuedOut, status_code=202, responses=WRITE
)
def generate(channel_id: uuid.UUID, body: GenerateIn, request: Request, db: Db, p: Edit) -> Any:
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    get_channel(db, channel_id)
    _not_stopped(db, channel_id)
    job = defer_in_transaction(
        db,
        "content.ideas",
        queue="agents",
        args={"channel_id": str(channel_id), "count": body.count, "fmt": body.format, "pillar": body.pillar},
    )
    record(
        db,
        actor=p.actor,
        action="ideas.generate_requested",
        entity_type="channel",
        entity_id=str(channel_id),
        channel_id=channel_id,
        details=body.model_dump(),
        request_id=request_id(request),
        ip=client_ip(request),
    )
    out = QueuedOut(job_id=job)
    idem.store(202, out.model_dump(mode="json"))
    db.commit()
    return out


@router.patch("/ideas/{idea_id}", response_model=IdeaOut, responses=WRITE)
def edit_idea(
    idea_id: uuid.UUID,
    body: IdeaIn,
    request: Request,
    db: Db,
    p: Edit,
    if_match_header: Annotated[str | None, Header(alias="If-Match")] = None,
) -> IdeaOut:
    expected = if_match(if_match_header)
    row = _idea(db, idea_id)
    if row.state not in EDITABLE:
        raise ProblemError(
            409, "NOT_EDITABLE", "Not editable", f"An idea that is {row.state} cannot be edited."
        )
    _no_promises(body)
    near = closest_idea(db, row.channel_id, body.title, exclude=row.id)
    values = {
        "title": body.title.strip(),
        "angle": body.angle.strip(),
        "format": body.format,
        "target_viewer": body.target_viewer,
        "pillar": body.pillar,
        "packaging_promise": body.packaging_promise.model_dump() if body.packaging_promise else None,
        "owner_value_add_prompt": body.owner_value_add_prompt,
        "similarity_max": near.score,
        "similar_to_id": near.idea_id,
    }
    try:
        update_versioned(db, VideoIdea, idea_id, expected, values)
    except VersionConflictError as exc:
        raise ProblemError(
            412, "VERSION_CONFLICT", "Changed elsewhere", "Reload and try again.", current_version=exc.current
        ) from exc
    db.refresh(row)
    _audit(request, db, p, "idea.edited", row, title=row.title)
    db.commit()
    return idea_out(db, row)


@router.post("/ideas/{idea_id}/commands/{cmd}", response_model=CommandOut, responses=WRITE)
def idea_command(
    idea_id: uuid.UUID,
    cmd: Literal["shortlist", "schedule", "approve", "discard"],
    request: Request,
    response: Response,
    db: Db,
    p: Edit,
    body: CommandIn | None = None,
) -> Any:
    """``approve`` needs ``content.approve``; it creates the project and queues its research."""
    body = body or CommandIn()
    if cmd == "approve" and not p.has("content.approve"):
        raise ProblemError(403, "FORBIDDEN", "Not allowed", "You may not approve ideas.")
    idem = Idempotency(db, request, p.user.id, {"cmd": cmd, **body.model_dump(mode="json")})
    if (replayed := idem.replay()) is not None:
        return replayed
    row = _idea(db, idea_id, lock=True)
    machine = MACHINES["video_idea"]
    payload: dict[str, Any] = {}
    if body.override_reason:
        payload["override_reason"] = body.override_reason
    event = {"shortlist": "shortlist", "schedule": "schedule", "discard": "discard"}.get(cmd, "approve")
    if cmd == "schedule":
        if body.date is None:
            raise ProblemError(
                400, "VALIDATION_ERROR", "Invalid request", "Pick a date to schedule the idea."
            )
        row.calendar_date = body.date
        db.flush()
    if cmd == "approve" and row.state == "SCHEDULED":
        event = "approve_scheduled"
    project_id: uuid.UUID | None = None
    jobs: list[int] = []
    try:
        result = engine.transition(
            db, machine, row.id, event, actor=p.actor, payload=payload, reason=body.override_reason
        )
        if cmd == "approve":
            from tubeforge_agents.content import start_project

            project = start_project(db, row.id, target_duration_s=body.target_duration_s, commit=False)
            project_id = project.id
            job = defer_in_transaction(
                db, "content.research", queue="agents", args={"project_id": str(project.id)}
            )
            jobs = [job] if job is not None else []
    except TransitionRejected as exc:
        db.rollback()
        raise rejected(exc) from exc
    db.refresh(row)
    _audit(request, db, p, f"idea.{cmd}", row, project_id=str(project_id) if project_id else None)
    out = CommandOut(
        idea=idea_out(db, row), transition_id=result.transition_id, project_id=project_id, job_ids=jobs
    )
    status = 202 if jobs else 200
    response.status_code = status
    idem.store(status, out.model_dump(mode="json"))
    db.commit()
    return out


# ----------------------------------------------------------------------------------- calendar
@router.get("/calendar", response_model=CalendarOut)
def calendar(
    db: Db,
    p: View,
    from_: Annotated[date, Query(alias="from")],
    to: date,
    channel_id: uuid.UUID | None = None,
) -> CalendarOut:
    if to < from_ or (to - from_).days > 120:
        raise ProblemError(400, "VALIDATION_ERROR", "Invalid range", "Pick a range of at most 120 days.")
    stmt = (
        select(VideoIdea)
        .where(
            VideoIdea.deleted_at.is_(None),
            VideoIdea.calendar_date.is_not(None),
            VideoIdea.calendar_date >= from_,
            VideoIdea.calendar_date <= to,
            VideoIdea.state != "DISCARDED",
        )
        .order_by(VideoIdea.calendar_date, VideoIdea.id)
    )
    if channel_id is not None:
        stmt = stmt.where(VideoIdea.channel_id == channel_id)
    items: list[CalendarItemOut] = []
    for idea in db.scalars(stmt.limit(500)):
        project = _project_of(db, idea.id)
        assert idea.calendar_date is not None
        items.append(
            CalendarItemOut(
                id=idea.id,
                date=idea.calendar_date,
                channel_id=idea.channel_id,
                title=idea.title,
                format=idea.format,
                state=idea.state,
                project_id=project.id if project else None,
                project_state=project.state if project else None,
            )
        )
    return CalendarOut(items=items)


@router.patch("/calendar/items/{idea_id}", response_model=CalendarItemOut, responses=WRITE)
def move_calendar_item(
    idea_id: uuid.UUID, body: DateIn, request: Request, db: Db, p: Edit
) -> CalendarItemOut:
    """Drag and drop: move a scheduled idea to another day."""
    row = _idea(db, idea_id, lock=True)
    if row.calendar_date is None or row.state in ("PRODUCED", "DISCARDED"):
        raise ProblemError(409, "NOT_EDITABLE", "Not on the calendar", "Only a scheduled idea can be moved.")
    before = row.calendar_date
    row.calendar_date = body.date
    row.version += 1
    _audit(request, db, p, "calendar.moved", row, before=str(before), after=str(body.date))
    db.commit()
    project = _project_of(db, row.id)
    return CalendarItemOut(
        id=row.id, date=body.date, channel_id=row.channel_id, title=row.title, format=row.format,
        state=row.state, project_id=project.id if project else None,
        project_state=project.state if project else None,
    )  # fmt: skip


# ---------------------------------------------------------------------------------- replicate
def _winners(db: Session, channel_id: uuid.UUID) -> list[WinnerOut]:
    rows = db.scalars(
        select(VideoProject)
        .where(
            VideoProject.channel_id == channel_id,
            VideoProject.youtube_video_id.is_not(None),
            VideoProject.is_test.is_(False),
            VideoProject.deleted_at.is_(None),
        )
        .order_by(VideoProject.updated_at.desc())
        .limit(50)
    )
    return [
        WinnerOut(youtube_video_id=str(r.youtube_video_id), title=r.working_title, project_id=r.id)
        for r in rows
    ]


@router.get("/channels/{channel_id}/replicate", response_model=ReplicateOut)
def replicate_overview(channel_id: uuid.UUID, db: Db, p: View) -> ReplicateOut:
    """The channel's own videos (winners) and the variations made from them. Outlier analytics
    (views, multiple) arrive with Phase 13; the list is the channel's own uploads only (ADR-0015)."""
    get_channel(db, channel_id)
    variations = db.scalars(
        select(VideoIdea)
        .where(
            VideoIdea.channel_id == channel_id,
            VideoIdea.source == "REPLICATE",
            VideoIdea.deleted_at.is_(None),
        )
        .order_by(VideoIdea.id.desc())
        .limit(100)
    )
    return ReplicateOut(winners=_winners(db, channel_id), variations=[idea_out(db, v) for v in variations])


@router.post(
    "/channels/{channel_id}/ideas/replicate", response_model=QueuedOut, status_code=202, responses=WRITE
)
def replicate(channel_id: uuid.UUID, body: ReplicateIn, request: Request, db: Db, p: Edit) -> Any:
    """Variations of one of the channel's own videos. Ideas too close to the source (≥ the method's
    ``variation_max``) are dropped by the worker and listed in the job result."""
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    get_channel(db, channel_id)
    source = db.scalar(
        select(VideoProject).where(
            VideoProject.channel_id == channel_id,
            VideoProject.youtube_video_id == body.youtube_video_id,
            VideoProject.is_test.is_(False),
            VideoProject.deleted_at.is_(None),
        )
    )
    if source is None:
        raise not_found("That video is not one of this channel's own videos.")
    _not_stopped(db, channel_id)
    idea = db.get(VideoIdea, source.idea_id) if source.idea_id else None
    variation = {
        "youtube_video_id": body.youtube_video_id,
        "title": source.working_title,
        "kind": body.kind,
        "angle": (body.note or (idea.angle if idea else ""))[:500],
        "format": source.format,
    }
    job = defer_in_transaction(
        db,
        "content.ideas",
        queue="agents",
        args={"channel_id": str(channel_id), "count": body.count, "variation": variation},
    )
    record(
        db,
        actor=p.actor,
        action="ideas.replicate_requested",
        entity_type="channel",
        entity_id=str(channel_id),
        channel_id=channel_id,
        details={"youtube_video_id": body.youtube_video_id, "kind": body.kind},
        request_id=request_id(request),
        ip=client_ip(request),
    )
    out = QueuedOut(job_id=job)
    idem.store(202, out.model_dump(mode="json"))
    db.commit()
    return out


# ------------------------------------------------------------------------------- trend → idea
def trend_to_idea(db: Session, trend: TrendItem, now: datetime | None = None) -> VideoIdea:
    """The owner turns an active trend into an idea (it expires with the trend)."""
    now = now or datetime.now(UTC)
    if trend.channel_id is None:
        raise ProblemError(409, "NO_CHANNEL", "No channel", "This trend is not linked to a channel.")
    title = trend.topic.strip()[:100]
    if len(title) < 5:
        title = f"{title} — what changed"[:100]
    near = closest_idea(db, trend.channel_id, title)
    row = VideoIdea(
        id=uuid7(),
        channel_id=trend.channel_id,
        state="SUGGESTED",
        title=title,
        angle=(trend.summary or trend.topic)[:500],
        format="SHORT",
        source="OWNER",
        trend_item_id=trend.id,
        expires_at=trend.expires_at,
        similarity_max=near.score,
        similar_to_id=near.idea_id,
    )
    db.add(row)
    trend.status = "USED"
    db.flush()
    return row
