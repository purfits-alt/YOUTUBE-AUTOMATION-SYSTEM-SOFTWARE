"""Job queue (ADR-0004): Procrastinate on PostgreSQL behind a small ``JobQueue`` interface.

Queue names follow SYSTEM_ARCHITECTURE §4-E. The light worker serves every queue except
``heavy``; the heavy worker serves ``heavy`` only, with concurrency 1.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any, Protocol

import procrastinate

QUEUE_ORCHESTRATOR = "orchestrator"
QUEUE_AGENTS = "agents"
QUEUE_YOUTUBE = "youtube"
QUEUE_NOTIFY = "notify"
QUEUE_MAINTENANCE = "maintenance"
QUEUE_HEAVY = "heavy"

LIGHT_QUEUES: tuple[str, ...] = (
    QUEUE_ORCHESTRATOR,
    QUEUE_AGENTS,
    QUEUE_YOUTUBE,
    QUEUE_NOTIFY,
    QUEUE_MAINTENANCE,
)
HEAVY_QUEUES: tuple[str, ...] = (QUEUE_HEAVY,)
WORKER_PROFILES: dict[str, tuple[tuple[str, ...], int]] = {
    "light": (LIGHT_QUEUES, 4),
    "heavy": (HEAVY_QUEUES, 1),
}

TASK_NAMESPACE = "tf"


class JobQueue(Protocol):
    """What the rest of TubeForge depends on — never Procrastinate directly."""

    async def enqueue(self, task_name: str, *, queue: str, idempotency_key: str, **kwargs: Any) -> int: ...


def ensure_windows_event_loop_policy() -> None:
    """psycopg's async mode needs the selector event loop on Windows (ADR-0004 spike)."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined,unused-ignore]


def build_app(libpq_dsn: str) -> procrastinate.App:
    # Imported here: the task module imports queue constants from this module.
    from tubeforge_workers.tasks import make_blueprint

    app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=libpq_dsn))
    app.add_tasks_from(make_blueprint(), namespace=TASK_NAMESPACE)
    return app


def task_name(name: str) -> str:
    return f"{TASK_NAMESPACE}:{name}"


class ProcrastinateQueue:
    """``JobQueue`` implementation.

    Phase 1: ``idempotency_key`` maps to Procrastinate's queueing lock, which prevents a
    duplicate *waiting* job. Phase 5 adds the durable ``job_meta.idempotency_key`` UNIQUE
    constraint (DATABASE_SCHEMA §9) for exactly-once semantics across job states.
    """

    def __init__(self, app: procrastinate.App) -> None:
        self._app = app

    async def enqueue(self, task_name: str, *, queue: str, idempotency_key: str, **kwargs: Any) -> int:
        task = self._app.tasks[task_name if ":" in task_name else f"{TASK_NAMESPACE}:{task_name}"]
        job_id: int = await task.configure(queue=queue, queueing_lock=idempotency_key).defer_async(**kwargs)
        return job_id


def defer_in_transaction(
    db: Any,
    name: str,
    *,
    queue: str,
    args: dict[str, Any],
    queueing_lock: str | None = None,
    lock: str | None = None,
) -> int | None:
    """Create a Procrastinate job in the caller's SQLAlchemy transaction (transactional outbox).

    The job only becomes visible to workers when the caller commits, so a request that fails after
    this call leaves no orphan job. Returns None when ``queueing_lock`` already has a waiting job.
    """
    import json

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    stmt = text(
        "SELECT unnest(procrastinate_defer_jobs_v1(ARRAY[ROW(:queue, :task, 0, :lock, :qlock,"
        " CAST(:args AS jsonb), NULL)::procrastinate_job_to_defer_v1])) AS id"
    )
    params = {
        "queue": queue,
        "task": task_name(name),
        "lock": lock,
        "qlock": queueing_lock,
        "args": json.dumps(args),
    }
    try:
        with db.begin_nested():
            job_id = db.execute(stmt, params).scalar_one()
    except IntegrityError:
        return None
    return int(job_id)
