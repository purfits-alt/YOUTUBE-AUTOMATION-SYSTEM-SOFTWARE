"""Worker tasks: Phase 1 smoke tasks and the maintenance jobs (Phase 4: token health).

Real agent and media tasks arrive in Phases 5–9 (BACKEND_SPECIFICATION §5).

A Procrastinate blueprint is modified when it is attached to an app (task names get the
namespace), so :func:`make_blueprint` returns a fresh one for every app instance.
"""

from __future__ import annotations

import procrastinate

from tubeforge.queue import QUEUE_AGENTS, QUEUE_HEAVY, QUEUE_MAINTENANCE, QUEUE_ORCHESTRATOR, QUEUE_YOUTUBE
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
        (
            "mnt.retention.purge_research_docs",
            maintenance.RESEARCH_PURGE_CRON,
            maintenance.purge_research_documents,
        ),
        ("orch.reconcile", maintenance.RECONCILE_CRON, maintenance.reconcile),
        ("orch.approvals_expire", maintenance.APPROVALS_CRON, maintenance.expire_approvals),
        ("a32.usage_scan", maintenance.A32_CRON, maintenance.a32_usage_scan),
        ("a03.trend_scan", maintenance.TREND_SCAN_CRON, maintenance.trend_scan),
    ]
    for name, cron, fn in periodic:
        queue = QUEUE_ORCHESTRATOR if name.startswith("orch.") else QUEUE_MAINTENANCE
        bp.periodic(cron=cron)(bp.task(name=name, queue=queue)(fn))
    bp.task(name="yt.upload", queue=QUEUE_YOUTUBE)(maintenance.upload)
    bp.task(name="agent.run", queue=QUEUE_AGENTS)(maintenance.run_agent)
    bp.task(name="research.discover", queue=QUEUE_AGENTS)(maintenance.discover)
    bp.task(name="research.blueprint", queue=QUEUE_AGENTS)(maintenance.blueprint)
    bp.task(name="research.keywords", queue=QUEUE_AGENTS)(maintenance.keywords)
    bp.task(name="research.trend_scan", queue=QUEUE_AGENTS)(maintenance.trend_scan_one)
    return bp
