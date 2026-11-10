"""Reconciler (WORKFLOW_STATE_MACHINE rule 3): every 2 minutes, make sure every entity whose state
expects a job has exactly one live job.

1. **Stalled jobs** — a job marked running whose worker is gone (no heartbeat for
   ``STALLED_AFTER``) is handed back to the queue with Procrastinate's own retry function: the
   same job runs again, exactly once, and keeps its lock.
2. **Lost jobs** — an entity in a job-expecting state with no waiting or running job gets one
   (``queueing_lock`` prevents duplicates).

Nothing is re-enqueued while Emergency Stop is on.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from tubeforge.audit import SYSTEM, record
from tubeforge.db.models import UploadJob
from tubeforge.orchestrator.engine import emergency_stop_active
from tubeforge.queue import QUEUE_YOUTUBE, defer_in_transaction, task_name

STALLED_AFTER = timedelta(minutes=5)


@dataclass(frozen=True)
class Expectation:
    """Entities of ``model`` in ``states`` need a ``task`` job identified by ``arg``."""

    model: type[Any]
    states: tuple[str, ...]
    task: str
    queue: str
    arg: str
    lock: Callable[[Any], str | None]
    queueing_lock: Callable[[Any], str]


EXPECTATIONS: list[Expectation] = [
    Expectation(
        UploadJob,
        ("PREFLIGHT", "SESSION_STARTED", "TRANSFERRING", "RESUMING"),
        "yt.upload",
        QUEUE_YOUTUBE,
        "upload_job_id",
        lambda job: f"upload-channel:{job.channel_id}",
        lambda job: f"upload-job:{job.id}",
    ),
]


@dataclass
class ReconcileResult:
    retried_stalled: list[int] = field(default_factory=list)
    enqueued: list[str] = field(default_factory=list)
    skipped_emergency_stop: bool = False


def _stalled_jobs(db: Session, tasks: list[str], now: datetime) -> list[int]:
    rows: Any = db.execute(
        text(
            "SELECT job.id FROM procrastinate_jobs job "
            "LEFT JOIN procrastinate_workers w ON w.id = job.worker_id "
            "WHERE job.status = 'doing' AND job.task_name = ANY(:tasks) "
            "AND (w.id IS NULL OR w.last_heartbeat < :cutoff)"
        ),
        {"tasks": tasks, "cutoff": now - STALLED_AFTER},
    ).scalars()
    return [int(r) for r in rows]


def _has_live_job(db: Session, exp: Expectation, entity_id: str) -> bool:
    found = db.execute(
        text(
            "SELECT 1 FROM procrastinate_jobs WHERE task_name = :task AND status IN ('todo', 'doing') "
            "AND args ->> :arg = :id LIMIT 1"
        ),
        {"task": task_name(exp.task), "arg": exp.arg, "id": entity_id},
    ).first()
    return found is not None


def reconcile(db: Session, *, now: datetime | None = None) -> ReconcileResult:
    now = now or datetime.now(UTC)
    result = ReconcileResult()
    if emergency_stop_active(db):
        result.skipped_emergency_stop = True
        return result
    tasks = [task_name(e.task) for e in EXPECTATIONS]
    for job_id in _stalled_jobs(db, tasks, now):
        db.execute(text("SELECT procrastinate_retry_job_v2(:id, now(), NULL, NULL, NULL)"), {"id": job_id})
        result.retried_stalled.append(job_id)
    for exp in EXPECTATIONS:
        entities: list[Any] = list(db.scalars(select(exp.model).where(exp.model.state.in_(exp.states))))
        for entity in entities:
            eid = str(entity.id)
            if _has_live_job(db, exp, eid):
                continue
            job = defer_in_transaction(
                db,
                exp.task,
                queue=exp.queue,
                args={exp.arg: eid},
                queueing_lock=exp.queueing_lock(entity),
                lock=exp.lock(entity),
            )
            if job is not None:
                result.enqueued.append(eid)
    if result.retried_stalled or result.enqueued:
        record(
            db,
            actor=SYSTEM,
            action="orch.reconciled",
            entity_type="system",
            entity_id="reconciler",
            details={"retried_stalled": result.retried_stalled, "enqueued": result.enqueued},
        )
    db.flush()
    return result
