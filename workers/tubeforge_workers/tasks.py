"""Phase 1 tasks: smoke-test tasks that prove each worker profile can run jobs.

Real agent and media tasks arrive in Phases 5–9 (BACKEND_SPECIFICATION §5).

A Procrastinate blueprint is modified when it is attached to an app (task names get the
namespace), so :func:`make_blueprint` returns a fresh one for every app instance.
"""

from __future__ import annotations

import procrastinate

from tubeforge.queue import QUEUE_HEAVY, QUEUE_MAINTENANCE


def ping(message: str) -> str:
    """Light-queue smoke task."""
    return f"pong:{message}"


def heavy_ping(message: str) -> str:
    """Heavy-queue smoke task (no real media work in Phase 1)."""
    return f"heavy-pong:{message}"


def make_blueprint() -> procrastinate.Blueprint:
    bp = procrastinate.Blueprint()
    bp.task(name="mnt.ping", queue=QUEUE_MAINTENANCE)(ping)
    bp.task(name="heavy.ping", queue=QUEUE_HEAVY)(heavy_ping)
    return bp
