"""Pipeline view (owner request 2026-11-18, ADR-0031): every video project on one production line.

Each project shows its current station, the live percentage and stage of the job working on it, the
station that comes next and who acts there (TubeForge or the owner). Stations move on by themselves
when a job finishes (the orchestrator engine does that); at owner stations the line waits for the
owner's approval, which is never skipped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tubeforge.api.deps import Db, Principal, require
from tubeforge.db.models import Channel, JobProgress, VideoProject
from tubeforge.progress import TRACKED

router = APIRouter(tags=["pipeline"])
View = Annotated[Principal, Depends(require("content.view"))]

#: The phase whose stations are built. Later stations are shown, marked "arrives in Phase N".
BUILT_PHASE = 7
QUEUED_HINT_AFTER = timedelta(minutes=2)
STALLED_AFTER = timedelta(minutes=10)
RECENT_JOBS = timedelta(hours=24)
FAST_REFRESH_S, SLOW_REFRESH_S = 3, 20

Who = Literal["TUBEFORGE", "OWNER"]
JobStatus = Literal["QUEUED", "RUNNING", "DONE", "FAILED", "WAITING", "STALLED"]
Activity = Literal[
    "QUEUED", "WORKING", "STALLED", "STOPPED", "WAITING",
    "YOUR_TURN", "NOT_BUILT", "PAUSED", "BLOCKED", "DONE",
]  # fmt: skip
StepStatus = Literal["done", "current", "next", "later"]
#: State board buckets: not started yet vs being worked on (stopped work stays here, flagged).
INBOX_ACTIVITIES = {"QUEUED", "YOUR_TURN", "NOT_BUILT", "PAUSED"}
ATTENTION_ACTIVITIES = {"STALLED", "STOPPED", "WAITING", "BLOCKED"}


@dataclass(frozen=True)
class Station:
    key: str
    label: str
    who: Who
    states: tuple[str, ...]
    phase: int
    job: str | None = None


STATIONS: tuple[Station, ...] = (
    Station("research", "Research", "TUBEFORGE", ("IDEA", "RESEARCHING"), 7, "content.research"),
    Station("research_review", "Check the research", "OWNER", ("RESEARCH_REVIEW",), 7),
    Station("script", "Script writing", "TUBEFORGE", ("SCRIPTING",), 7, "content.script"),
    Station("script_review", "Approve the script", "OWNER", ("SCRIPT_REVIEW",), 7, "content.fact_check"),
    Station("storyboard", "Storyboard", "TUBEFORGE", ("STORYBOARDING",), 8),
    Station("visuals", "Visuals", "TUBEFORGE", ("ASSET_GENERATION",), 8),
    Station("voice", "Voice-over", "TUBEFORGE", ("VOICEOVER",), 8),
    Station("edit", "Video edit", "TUBEFORGE", ("ASSEMBLY",), 9),
    Station("cut_review", "Check the rough cut", "OWNER", ("ROUGH_CUT_REVIEW", "EXTERNAL_EDITING"), 9),
    Station("render", "Render", "TUBEFORGE", ("RENDERING",), 9),
    Station("package", "Thumbnail & SEO", "TUBEFORGE", ("PACKAGING",), 10),
    Station("audit", "Quality & policy checks", "TUBEFORGE", ("QC_AUDIT", "BLOCKED"), 11),
    Station("approval", "Approve publishing", "OWNER", ("READY_FOR_APPROVAL", "APPROVED"), 12),
    Station("upload", "Upload", "TUBEFORGE", ("UPLOADING", "PROCESSING", "SCHEDULED", "PRIVATE_DONE"), 12),
    Station("analytics", "Analytics", "TUBEFORGE", ("PUBLISHED", "ANALYZING", "ARCHIVED"), 13),
)
STATION_OF = {state: i for i, s in enumerate(STATIONS) for state in s.states}
STATION_INDEX = {s.key: i for i, s in enumerate(STATIONS)}
MAX_PROJECTS = 300
HIDDEN_STATES = ("CANCELLED",)


# ------------------------------------------------------------------------------------- models
class JobProgressOut(BaseModel):
    id: uuid.UUID
    kind: str
    label: str
    entity_type: str
    entity_id: uuid.UUID
    project_id: uuid.UUID | None
    status: JobStatus
    pct: int
    stage: str
    message: str | None
    hint: str | None = None
    eta_s: int | None = None
    queued_at: datetime
    started_at: datetime | None
    updated_at: datetime
    finished_at: datetime | None
    link: str | None = None


class BoardItemOut(BaseModel):
    id: uuid.UUID
    title: str
    activity: Activity
    pct: int | None = None


class StationBoardOut(BaseModel):
    """One station's card on the state board (owner request 2026-11-18)."""

    received_from: str | None = Field(description="Label of the station the inbox comes from.")
    forwards_to: str | None = Field(description="Label of the station work is handed to.")
    inbox: list[BoardItemOut] = Field(default_factory=list, description="Arrived here, not started yet.")
    in_progress: list[BoardItemOut] = Field(default_factory=list, description="Being worked on here.")
    attention: int = Field(default=0, description="In progress but stopped, stalled or blocked.")
    complete: int = Field(default=0, description="Videos that finished this station.")
    forwarded: list[BoardItemOut] = Field(
        default_factory=list, description="Finished here and now at the next station."
    )


class StationOut(BaseModel):
    key: str
    label: str
    who: Who
    phase: int
    ready: bool
    count: int = 0
    board: StationBoardOut | None = None


class PipelineStepOut(BaseModel):
    key: str
    status: StepStatus


class PipelineProjectOut(BaseModel):
    id: uuid.UUID
    title: str
    channel_id: uuid.UUID
    channel_name: str
    format: str
    state: str
    station: str
    activity: Activity
    progress: JobProgressOut | None
    next: StationOut | None
    steps: list[PipelineStepOut]
    link: str
    updated_at: datetime


class ChannelCardOut(BaseModel):
    """One channel's state across the whole line (owner request 2026-11-27: a card per channel on top)."""

    id: uuid.UUID
    name: str
    state: str = Field(description="The channel's own state (ACTIVE, ONBOARDING, PAUSED, …).")
    private_only: bool
    videos: int = Field(default=0, description="Videos on the line (not cancelled).")
    working: int = Field(default=0, description="A job is running on them now.")
    queued: int = Field(default=0, description="Waiting for a free worker.")
    your_turn: int = Field(default=0, description="Waiting for the owner's review or approval.")
    attention: int = Field(default=0, description="Stopped, stalled, waiting for a limit or blocked.")
    next_phase: int = Field(default=0, description="Ready for a station that arrives in a later phase.")
    published: int = 0
    paused: int = 0


class PipelineOut(BaseModel):
    channels: list[ChannelCardOut] = Field(
        default_factory=list, description="Every channel with its state and work in progress (all channels)."
    )
    channel_id: uuid.UUID | None = Field(default=None, description="The channel the rest of the page shows.")
    stations: list[StationOut]
    projects: list[PipelineProjectOut]
    jobs: list[JobProgressOut]
    refresh_s: int
    built_phase: int = BUILT_PHASE


# ------------------------------------------------------------------------------------ helpers
def _link(row: JobProgress) -> str | None:
    if row.project_id is not None:
        return f"/projects/{row.project_id}/script"
    return {
        "channel": f"/channels/{row.entity_id}/ideas",
        "niche_report": "/discovery",
        "niche_candidate": "/strategies",
    }.get(row.entity_type)


def _average_seconds(db: Session, kind: str) -> float | None:
    recent = (
        select(JobProgress.started_at, JobProgress.finished_at)
        .where(JobProgress.kind == kind, JobProgress.status == "DONE", JobProgress.started_at.is_not(None))
        .order_by(JobProgress.finished_at.desc())
        .limit(10)
        .subquery()
    )
    avg = db.scalar(select(func.avg(func.extract("epoch", recent.c.finished_at - recent.c.started_at))))
    return float(avg) if avg is not None else None


def job_out(
    db: Session, row: JobProgress, now: datetime, averages: dict[str, float | None]
) -> JobProgressOut:
    status: JobStatus = row.status  # type: ignore[assignment]
    hint: str | None = None
    eta: int | None = None
    if row.status == "QUEUED" and now - row.queued_at > QUEUED_HINT_AFTER:
        hint = (
            "Waiting for a worker. If this does not start soon, check that TubeForge is running "
            "(tubeforge.ps1 status) — the job starts as soon as a worker is free."
        )
    elif row.status == "RUNNING" and now - row.updated_at > STALLED_AFTER:
        status = "STALLED"
        minutes = int((now - row.updated_at).total_seconds() // 60)
        hint = (
            f"No news for {minutes} minutes. The worker may have stopped: restart TubeForge "
            "(tubeforge.ps1 stop, then start). Unfinished jobs are picked up again."
        )
    if row.status == "RUNNING" and status == "RUNNING" and row.started_at is not None:
        if row.kind not in averages:
            averages[row.kind] = _average_seconds(db, row.kind)
        avg = averages[row.kind]
        if avg is not None:
            eta = max(5, int(avg - (now - row.started_at).total_seconds()))
    return JobProgressOut(
        id=row.id,
        kind=row.kind,
        label=TRACKED.get(row.kind, row.kind),
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        project_id=row.project_id,
        status=status,
        pct=row.pct,
        stage=row.stage,
        message=row.message,
        hint=hint,
        eta_s=eta,
        queued_at=row.queued_at,
        started_at=row.started_at,
        updated_at=row.updated_at,
        finished_at=row.finished_at,
        link=_link(row),
    )


def latest_job(db: Session, project_id: uuid.UUID) -> JobProgress | None:
    return db.scalar(
        select(JobProgress)
        .where(JobProgress.project_id == project_id)
        .order_by(JobProgress.queued_at.desc())
        .limit(1)
    )


def project_progress(
    db: Session,
    project: VideoProject,
    now: datetime | None = None,
    averages: dict[str, float | None] | None = None,
) -> JobProgressOut | None:
    """The live job of the project's current station, if any (also a stopped one, with the reason)."""
    now = now or datetime.now(UTC)
    row = latest_job(db, project.id)
    if row is None:
        return None
    station = STATIONS[STATION_OF.get(_effective_state(project), 0)]
    if row.kind != station.job:
        return None
    if row.status == "DONE" and (row.finished_at is None or now - row.finished_at > timedelta(minutes=2)):
        return None
    return job_out(db, row, now, averages if averages is not None else {})


def _effective_state(project: VideoProject) -> str:
    if project.state in ("PAUSED", "FAILED") and project.resume_to_state:
        return project.resume_to_state
    return project.state


def _station_out(i: int, count: int = 0) -> StationOut:
    s = STATIONS[i]
    return StationOut(
        key=s.key, label=s.label, who=s.who, phase=s.phase, ready=s.phase <= BUILT_PHASE, count=count
    )


def _activity(project: VideoProject, index: int, progress: JobProgressOut | None) -> Activity:
    station = STATIONS[index]
    if project.state == "PAUSED":
        return "PAUSED"
    if project.state == "FAILED":
        return "STOPPED"
    if project.state == "BLOCKED":
        return "BLOCKED"
    if project.state in ("PUBLISHED", "ANALYZING", "ARCHIVED"):
        return "DONE"
    if station.phase > BUILT_PHASE:
        return "NOT_BUILT"
    if project.state == "IDEA":
        return "YOUR_TURN"  # the owner presses Start
    if station.who == "OWNER":
        if progress is not None and progress.status in ("QUEUED", "RUNNING"):
            return "WORKING"  # e.g. fact-checking the owner's own edit
        return "YOUR_TURN"
    if progress is None:
        return "STALLED"  # a TubeForge station with no job: it was lost or never queued
    return {
        "QUEUED": "QUEUED",
        "RUNNING": "WORKING",
        "STALLED": "STALLED",
        "FAILED": "STOPPED",
        "WAITING": "WAITING",
        "DONE": "WORKING",
    }[progress.status]  # type: ignore[return-value]


def _board(projects: list[PipelineProjectOut]) -> list[StationBoardOut]:
    """Inbox / in progress / complete / forwarded for every station, from where each video is now."""
    index = {s.key: i for i, s in enumerate(STATIONS)}
    cards = [
        StationBoardOut(
            received_from=STATIONS[i - 1].label if i > 0 else "Approved idea",
            forwards_to=STATIONS[i + 1].label if i + 1 < len(STATIONS) else None,
        )
        for i in range(len(STATIONS))
    ]
    for item in projects:
        at = index[item.station]
        entry = BoardItemOut(
            id=item.id,
            title=item.title,
            activity=item.activity,
            pct=item.progress.pct if item.progress else None,
        )
        if item.activity == "DONE":  # published: every station is complete
            for card in cards:
                card.complete += 1
            continue
        card = cards[at]
        if item.activity in INBOX_ACTIVITIES:
            card.inbox.append(entry)
        else:
            card.in_progress.append(entry)
            card.attention += item.activity in ATTENTION_ACTIVITIES
        for done in range(at):
            cards[done].complete += 1
        if at > 0:
            cards[at - 1].forwarded.append(entry)
    return cards


def _channel_cards(db: Session, projects: list[PipelineProjectOut]) -> list[ChannelCardOut]:
    """A card per channel (also channels with no videos yet), counted from where each video is now."""
    cards = {
        c.id: ChannelCardOut(id=c.id, name=c.name, state=c.state, private_only=c.private_only_mode)
        for c in db.scalars(select(Channel).where(Channel.deleted_at.is_(None)).order_by(Channel.name))
    }
    field = {
        "WORKING": "working",
        "QUEUED": "queued",
        "YOUR_TURN": "your_turn",
        "NOT_BUILT": "next_phase",
        "DONE": "published",
        "PAUSED": "paused",
        **{a: "attention" for a in ATTENTION_ACTIVITIES},
    }
    for item in projects:
        card = cards.get(item.channel_id)
        if card is None:
            continue
        card.videos += 1
        name = field[item.activity]
        setattr(card, name, getattr(card, name) + 1)
    return list(cards.values())


# ------------------------------------------------------------------------------------- routes
@router.get("/pipeline", response_model=PipelineOut)
def pipeline(db: Db, p: View, channel_id: uuid.UUID | None = None) -> PipelineOut:
    """Every active video project on the production line, with live job progress."""
    now = datetime.now(UTC)
    stmt = (
        select(VideoProject, Channel.name)
        .join(Channel, Channel.id == VideoProject.channel_id)
        .where(
            VideoProject.deleted_at.is_(None),
            VideoProject.is_test.is_(False),
            VideoProject.state.not_in(HIDDEN_STATES),
        )
        .order_by(VideoProject.updated_at.desc())
        .limit(MAX_PROJECTS)
    )
    averages: dict[str, float | None] = {}
    counts = [0] * len(STATIONS)
    projects: list[PipelineProjectOut] = []
    for project, channel_name in db.execute(stmt).all():
        index = STATION_OF.get(_effective_state(project), 0)
        counts[index] += 1
        progress = project_progress(db, project, now, averages)
        activity = _activity(project, index, progress)
        steps = [
            PipelineStepOut(
                key=s.key,
                status="done"
                if i < index
                else "current"
                if i == index
                else "next"
                if i == index + 1
                else "later",
            )
            for i, s in enumerate(STATIONS)
        ]
        projects.append(
            PipelineProjectOut(
                id=project.id,
                title=project.working_title,
                channel_id=project.channel_id,
                channel_name=channel_name,
                format=project.format,
                state=project.state,
                station=STATIONS[index].key,
                activity=activity,
                progress=progress,
                next=_station_out(index + 1) if index + 1 < len(STATIONS) else None,
                steps=steps,
                link=f"/projects/{project.id}/script",
                updated_at=project.updated_at,
            )
        )
    cards = _channel_cards(db, projects)
    if channel_id:
        projects = [x for x in projects if x.channel_id == channel_id]
        counts = [0] * len(STATIONS)
        for x in projects:
            counts[STATION_INDEX[x.station]] += 1
    board = _board(projects)
    jobs_stmt = (
        select(JobProgress)
        .where(JobProgress.project_id.is_(None), JobProgress.queued_at > now - RECENT_JOBS)
        .order_by(JobProgress.queued_at.desc())
        .limit(10)
    )
    if channel_id:
        jobs_stmt = jobs_stmt.where(
            (JobProgress.entity_type != "channel") | (JobProgress.entity_id == channel_id)
        )
    jobs = [job_out(db, r, now, averages) for r in db.scalars(jobs_stmt)]
    busy = any(x.progress and x.progress.status in ("QUEUED", "RUNNING") for x in projects) or any(
        j.status in ("QUEUED", "RUNNING") for j in jobs
    )
    return PipelineOut(
        channels=cards,
        channel_id=channel_id,
        stations=[
            _station_out(i, counts[i]).model_copy(update={"board": board[i]}) for i in range(len(STATIONS))
        ],
        projects=projects,
        jobs=jobs,
        refresh_s=FAST_REFRESH_S if busy else SLOW_REFRESH_S,
    )
