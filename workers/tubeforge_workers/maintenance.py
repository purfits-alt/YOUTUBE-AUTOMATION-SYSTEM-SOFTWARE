"""Maintenance and YouTube jobs (BACKEND_SPECIFICATION §5; retention rules DATABASE_SCHEMA §15).

Procrastinate evaluates cron in UTC: 02:00 UTC = 07:00 PKT.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.config import get_settings
from tubeforge.db.session import get_engine
from tubeforge.gateway.core import Gateway
from tubeforge.logging import get_logger
from tubeforge.notifications import notify_owners
from tubeforge.orchestrator import approvals, reconciler
from tubeforge.research.fetcher import ResearchFetcher
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
TREND_SCAN_CRON = "0 1 * * *"  # 06:00 PKT (UTC+5), CHANNEL_DISCOVERY_SPEC §5

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


@contextmanager
def _research() -> Iterator[tuple[Session, Gateway, ResearchFetcher]]:
    settings = get_settings()
    with (
        Session(get_engine(settings.database_url), expire_on_commit=False) as db,
        ResearchFetcher() as fetcher,
    ):
        yield db, Gateway(SecretBox(default_store(settings.env))), fetcher


def discover(report_id: str) -> str:
    """research.discover: one niche discovery report (A02)."""
    from tubeforge_agents.discovery import run_discovery

    with _research() as (db, gateway, fetcher):
        status = run_discovery(db, gateway, fetcher, uuid.UUID(report_id)).status
    log.info("research.discover", report_id=report_id, status=status)
    return status


def blueprint(candidate_id: str, owner_notes: str = "") -> str:
    """research.blueprint: A07 + A06 → blueprint DRAFT for a shortlisted candidate."""
    from tubeforge_agents.discovery import PipelineError, generate_blueprint

    with _research() as (db, gateway, _fetcher):
        try:
            result = generate_blueprint(db, gateway, uuid.UUID(candidate_id), owner_notes=owner_notes)
        except PipelineError as exc:
            notify_owners(
                db,
                event_type="research.blueprint_failed",
                severity="WARNING",
                title="The blueprint could not be made",
                body=exc.message[:300],
                dedup_key=f"blueprint:{candidate_id}:{exc.status}",
                link="/strategies",
            )
            db.commit()
            log.info("research.blueprint", candidate_id=candidate_id, status=exc.status)
            return exc.status
        status = f"DRAFT v{result.strategy.version} ({len(result.problems)} problems)"
    log.info("research.blueprint", candidate_id=candidate_id, status=status)
    return status


def keywords(channel_id: str, seeds: list[str]) -> int:
    """research.keywords: A05 keyword suggestions for one channel."""
    from tubeforge_agents.discovery import run_keywords

    with _research() as (db, gateway, _fetcher):
        return len(run_keywords(db, gateway, uuid.UUID(channel_id), seeds))


def trend_scan(timestamp: int) -> dict[str, int]:
    """a03.trend_scan: daily at 06:00 PKT for every ACTIVE channel with an approved blueprint."""
    from tubeforge_agents.discovery import PipelineError, run_trend_scan

    from tubeforge.db.models import Channel

    found: dict[str, int] = {}
    with _research() as (db, gateway, fetcher):
        for channel in db.scalars(select(Channel).where(Channel.state == "ACTIVE")).all():
            try:
                found[str(channel.id)] = len(run_trend_scan(db, gateway, fetcher, channel.id))
            except PipelineError as exc:
                log.info("a03.trend_scan.skipped", channel_id=str(channel.id), status=exc.status)
    log.info("a03.trend_scan", channels=len(found), items=sum(found.values()))
    return found


def upload(upload_job_id: str) -> str:
    """yt.upload: run or resume one upload job (Phase 4: private test uploads only)."""
    with _deps() as (db, box, google, youtube):
        job = uploads.run_upload_job(db, box, google, youtube, uuid.UUID(upload_job_id))
        state = job.state
    log.info("yt.upload", upload_job_id=upload_job_id, state=state)
    return state
