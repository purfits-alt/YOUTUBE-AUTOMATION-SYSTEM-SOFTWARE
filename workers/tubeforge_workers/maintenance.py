"""Maintenance and YouTube jobs (BACKEND_SPECIFICATION §5; retention rules DATABASE_SCHEMA §15).

Procrastinate evaluates cron in UTC: 02:00 UTC = 07:00 PKT.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from typing import Any

from sqlalchemy.orm import Session

from tubeforge.config import get_settings
from tubeforge.db.session import get_engine
from tubeforge.logging import get_logger
from tubeforge.orchestrator import approvals, reconciler
from tubeforge.secrets import SecretBox, default_store
from tubeforge.youtube import oauth, retention, uploads
from tubeforge.youtube.client import SafeYouTubeClient

OAUTH_HEALTH_CRON = "0 2 * * *"
REAUTH_CHECK_CRON = "30 2 * * *"
DELETION_CRON = "15 * * * *"
CACHE_PURGE_CRON = "45 * * * *"
PENDING_FLOWS_CRON = "*/10 * * * *"
RECONCILE_CRON = "*/2 * * * *"
APPROVALS_CRON = "5 * * * *"
A32_CRON = "*/15 * * * *"
RESEARCH_PURGE_CRON = "50 * * * *"

log = get_logger("tubeforge.jobs")


@contextmanager
def _deps() -> Iterator[tuple[Session, SecretBox, oauth.GoogleOAuth, SafeYouTubeClient]]:
    settings = get_settings()
    google, youtube = oauth.GoogleOAuth(), SafeYouTubeClient()
    try:
        with Session(get_engine(settings.database_url), expire_on_commit=False) as db:
            yield db, SecretBox(default_store(settings.env)), google, youtube
    finally:
        google.close()
        youtube.close()


def _run[T](name: str, fn: Callable[[Session, SecretBox, oauth.GoogleOAuth, SafeYouTubeClient], T]) -> T:
    with _deps() as (db, box, google, youtube):
        result = fn(db, box, google, youtube)
        db.commit()
    log.info(name, result=repr(result))
    return result


def token_health(timestamp: int) -> dict[str, Any]:
    """mnt.token_health: refresh every active YouTube token; warn before Testing-mode expiry."""
    return asdict(_run("mnt.token_health", lambda db, box, g, _y: oauth.token_health(db, box, g)))


def reauthorize_check(timestamp: int) -> dict[str, Any]:
    """mnt.retention.reauthorize_check: DP-3 30-day authorisation and video-existence check."""
    return asdict(
        _run(
            "mnt.retention.reauthorize_check",
            lambda db, box, g, y: retention.reauthorize_check(db, box, g, y),
        )
    )


def deletion_deadlines(timestamp: int) -> dict[str, Any]:
    """mnt.retention.deletion_deadlines: run open data-deletion tasks; alert when overdue (DP-4)."""
    return asdict(_run("mnt.retention.deletion_deadlines", lambda db, *_: retention.run_deletion_tasks(db)))


def purge_api_cache(timestamp: int) -> int:
    return _run("mnt.retention.purge_api_cache", lambda db, *_: retention.purge_api_cache(db))


def purge_pending_flows(timestamp: int) -> int:
    return _run("mnt.retention.oauth_pending_cleanup", lambda db, *_: retention.purge_pending_flows(db))


def purge_research_documents(timestamp: int) -> int:
    """mnt.retention.purge_research_docs: research documents older than 90 days are deleted."""
    from tubeforge.research.sources import purge_expired

    return _run("mnt.retention.purge_research_docs", lambda db, *_: purge_expired(db))


def reconcile(timestamp: int) -> dict[str, Any]:
    """orch.reconcile: re-enqueue lost or stalled jobs exactly once (WORKFLOW_STATE_MACHINE rule 3)."""
    return asdict(_run("orch.reconcile", lambda db, *_: reconciler.reconcile(db)))


def expire_approvals(timestamp: int) -> int:
    """orch.approvals_expire: PENDING approvals past their deadline (14 days) expire."""
    return _run("orch.approvals_expire", lambda db, *_: approvals.expire_due(db))


def a32_usage_scan(timestamp: int) -> dict[str, Any]:
    """a32.usage_scan: provider/YouTube/budget thresholds, re-verify and statement reminders."""
    from tubeforge_auditors import a32_cost

    report = _run("a32.usage_scan", lambda db, *_: a32_cost.scan(db))
    return {"alerts": report.alerts, "reverify_due": report.reverify_due}


def run_agent(
    agent_code: str, data: dict[str, Any], channel_id: str | None = None, idempotent: bool = True
) -> str:
    """agent.run: one agent task through the AI Provider Gateway; returns the run status."""
    from tubeforge_agents.base import run_agent as run
    from tubeforge_agents.hello import HANDLERS

    from tubeforge.gateway.core import Gateway

    with _deps() as (db, box, _google, _youtube):
        outcome = run(
            db,
            Gateway(box),
            HANDLERS[agent_code],
            data,
            channel_id=uuid.UUID(channel_id) if channel_id else None,
            idempotent=idempotent,
        )
        status = outcome.run.status
    log.info("agent.run", agent=agent_code, status=status)
    return status


def upload(upload_job_id: str) -> str:
    """yt.upload: run or resume one upload job (Phase 4: private test uploads only)."""
    with _deps() as (db, box, google, youtube):
        job = uploads.run_upload_job(db, box, google, youtube, uuid.UUID(upload_job_id))
        state = job.state
    log.info("yt.upload", upload_job_id=upload_job_id, state=state)
    return state
