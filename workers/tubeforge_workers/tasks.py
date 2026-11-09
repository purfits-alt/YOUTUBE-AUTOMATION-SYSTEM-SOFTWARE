"""Worker tasks: Phase 1 smoke tasks and the maintenance jobs (Phase 4: token health).

Real agent and media tasks arrive in Phases 5–9 (BACKEND_SPECIFICATION §5).

A Procrastinate blueprint is modified when it is attached to an app (task names get the
namespace), so :func:`make_blueprint` returns a fresh one for every app instance.
"""

from __future__ import annotations

import procrastinate

from tubeforge.queue import QUEUE_HEAVY, QUEUE_MAINTENANCE, QUEUE_YOUTUBE
from tubeforge_workers import maintenance


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
    periodic = [
        ("mnt.token_health", maintenance.OAUTH_HEALTH_CRON, maintenance.token_health),
        ("mnt.retention.reauthorize_check", maintenance.REAUTH_CHECK_CRON, maintenance.reauthorize_check),
        ("mnt.retention.deletion_deadlines", maintenance.DELETION_CRON, maintenance.deletion_deadlines),
        ("mnt.retention.purge_api_cache", maintenance.CACHE_PURGE_CRON, maintenance.purge_api_cache),
        (
            "mnt.retention.oauth_pending_cleanup",
            maintenance.PENDING_FLOWS_CRON,
            maintenance.purge_pending_flows,
        ),
    ]
    for name, cron, fn in periodic:
        bp.periodic(cron=cron)(bp.task(name=name, queue=QUEUE_MAINTENANCE)(fn))
    bp.task(name="yt.upload", queue=QUEUE_YOUTUBE)(maintenance.upload)
    return bp
