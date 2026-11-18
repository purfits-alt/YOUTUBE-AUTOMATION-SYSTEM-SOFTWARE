"""Live job progress for the pipeline view (owner request 2026-11-18, ADR-0031).

- When the API queues a tracked job, :func:`queued` adds a ``QUEUED`` row **in the same
  transaction** (rolled back together with the job).
- The worker wraps the job in :func:`track`: the row turns ``RUNNING``, and pipeline code calls
  :func:`report` with a percentage and a stage in plain words. Each report is written in its **own
  short transaction**, so the owner sees it at once while the job's main transaction is still open.
- When the job ends the row becomes ``DONE``, ``FAILED`` (with the reason) or ``WAITING`` (a free-tier
  limit or Emergency Stop; it continues later).

Pipeline code that runs without a tracker (unit tests, the API) is unaffected: :func:`report` does
nothing then. Progress rows never change workflow state: the orchestrator engine still does that.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, delete, select, update
from sqlalchemy.orm import Session

from tubeforge.db.ids import uuid7
from tubeforge.db.models import JobProgress, Script, ScriptVersion

#: Jobs shown in the pipeline, with the owner-facing label of each.
TRACKED: dict[str, str] = {
    "content.research": "Research",
    "content.script": "Script writing",
    "content.fact_check": "Fact check",
    "content.ideas": "New ideas",
    "research.discover": "Niche discovery",
    "research.blueprint": "Channel blueprint",
}

#: Job argument → the entity the job works on.
ENTITY_ARGS: tuple[tuple[str, str], ...] = (
    ("project_id", "video_project"),
    ("version_id", "script_version"),
    ("report_id", "niche_report"),
    ("candidate_id", "niche_candidate"),
    ("channel_id", "channel"),
)

QUEUED_STAGE = "Waiting for a free worker"
STALE_ACTIVE = {"QUEUED", "RUNNING"}


def _now() -> datetime:
    return datetime.now(UTC)


def entity_of(args: Mapping[str, Any]) -> tuple[str, uuid.UUID] | None:
    for arg, entity_type in ENTITY_ARGS:
        value = args.get(arg)
        if value:
            return entity_type, uuid.UUID(str(value))
    return None


def _project_for(db: Session, entity_type: str, entity_id: uuid.UUID) -> uuid.UUID | None:
    if entity_type == "video_project":
        return entity_id
    if entity_type == "script_version":
        return db.scalar(
            select(Script.project_id)
            .join(ScriptVersion, ScriptVersion.script_id == Script.id)
            .where(ScriptVersion.id == entity_id)
        )
    return None


def queued(db: Session, kind: str, args: Mapping[str, Any]) -> None:
    """Record a just-queued tracked job (call inside the transaction that queues it)."""
    if kind not in TRACKED:
        return
    entity = entity_of(args)
    if entity is None:
        return
    entity_type, entity_id = entity
    db.add(
        JobProgress(
            id=uuid7(),
            kind=kind,
            entity_type=entity_type,
            entity_id=entity_id,
            project_id=_project_for(db, entity_type, entity_id),
            status="QUEUED",
            pct=0,
            stage=QUEUED_STAGE,
        )
    )


class Tracker:
    """One running job's progress row. Each write is its own short transaction."""

    def __init__(self, engine: Engine, row_id: uuid.UUID) -> None:
        self._engine = engine
        self.row_id = row_id
        self.pct = 0
        self.finished = False

    def _write(self, **values: Any) -> None:
        with Session(self._engine) as s:
            s.execute(update(JobProgress).where(JobProgress.id == self.row_id).values(**values))
            s.commit()

    def step(self, pct: int, stage: str) -> None:
        if self.finished:
            return
        self.pct = max(self.pct, min(99, max(0, int(pct))))  # 100 only when it is really done
        self._write(pct=self.pct, stage=stage[:200], status="RUNNING")

    def finish(self, status: str = "DONE", message: str | None = None, stage: str | None = None) -> None:
        if self.finished:
            return
        self.finished = True
        values: dict[str, Any] = {"status": status, "finished_at": _now()}
        if status == "DONE":
            values.update(pct=100, stage=stage or "Done")
        else:
            values.update(stage=stage or ("Waiting" if status == "WAITING" else "Stopped"))
        if message is not None:
            values["message"] = message[:500]
        self._write(**values)


_current: ContextVar[Tracker | None] = ContextVar("tubeforge_progress", default=None)


def current() -> Tracker | None:
    return _current.get()


def report(pct: int, stage: str) -> None:
    """Report progress of the job running in this context (no-op without a tracker)."""
    tracker = _current.get()
    if tracker is not None:
        tracker.step(pct, stage)


def finish(status: str, message: str | None = None) -> None:
    """End the current job early as ``FAILED`` or ``WAITING`` with a reason (no-op without a tracker)."""
    tracker = _current.get()
    if tracker is not None:
        tracker.finish(status, message)


@contextmanager
def track(engine: Engine, kind: str, args: Mapping[str, Any]) -> Iterator[Tracker | None]:
    """Run a tracked job: QUEUED → RUNNING → DONE (or FAILED with the error, if it raises)."""
    entity = entity_of(args) if kind in TRACKED else None
    if entity is None:
        yield None
        return
    entity_type, entity_id = entity
    with Session(engine) as s:
        rows = list(
            s.scalars(
                select(JobProgress)
                .where(
                    JobProgress.kind == kind,
                    JobProgress.entity_id == entity_id,
                    JobProgress.status.in_(STALE_ACTIVE),
                )
                .order_by(JobProgress.queued_at.desc())
            )
        )
        row = next((r for r in rows if r.status == "QUEUED"), None)
        for old in rows:
            if old is not row:  # an earlier run that never finished (worker stopped)
                old.status, old.finished_at = "FAILED", _now()
                old.message = old.message or "Stopped before it finished; it was started again."
        if row is None:
            row = JobProgress(
                id=uuid7(),
                kind=kind,
                entity_type=entity_type,
                entity_id=entity_id,
                project_id=_project_for(s, entity_type, entity_id),
                status="RUNNING",
                pct=0,
                stage="Starting",
                queued_at=_now(),
            )
            s.add(row)
        row.status, row.pct, row.stage, row.started_at = "RUNNING", 1, "Starting", _now()
        s.commit()
        row_id = row.id
    tracker = Tracker(engine, row_id)
    token = _current.set(tracker)
    try:
        yield tracker
    except BaseException as exc:
        tracker.finish("FAILED", str(exc) or type(exc).__name__)
        raise
    else:
        tracker.finish("DONE")
    finally:
        _current.reset(token)


KEEP_FINISHED = timedelta(days=30)


def purge_finished(db: Session, now: datetime | None = None) -> int:
    """Retention (DATABASE_SCHEMA §15): finished progress rows older than 30 days are deleted."""
    cutoff = (now or _now()) - KEEP_FINISHED
    result = db.execute(
        delete(JobProgress).where(JobProgress.finished_at.is_not(None), JobProgress.finished_at < cutoff)
    )
    return int(getattr(result, "rowcount", 0) or 0)
