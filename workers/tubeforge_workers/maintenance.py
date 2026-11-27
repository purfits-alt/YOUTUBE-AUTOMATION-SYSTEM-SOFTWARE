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

from tubeforge import progress
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
PROGRESS_PURGE_CRON = "40 3 * * *"
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


def purge_job_progress(timestamp: int) -> int:
    """mnt.retention.purge_job_progress: finished pipeline progress rows older than 30 days."""
    return _run("mnt.retention.purge_job_progress", lambda db, *_: progress.purge_finished(db))


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


@contextmanager
def _tracked(kind: str, **args: Any) -> Iterator[None]:
    """Show this job's live progress in the pipeline (ADR-0031)."""
    with progress.track(get_engine(get_settings().database_url), kind, args):
        yield


def _stopped(exc: Any) -> None:
    """A pipeline step stopped: WAITING for a free-tier limit or Emergency Stop, else FAILED."""
    progress.finish("WAITING" if exc.status in ("WAITING_QUOTA", "STOPPED") else "FAILED", exc.message)


def discover(report_id: str) -> str:
    """research.discover: one niche discovery report (A02)."""
    from tubeforge_agents.discovery import run_discovery

    with _tracked("research.discover", report_id=report_id), _research() as (db, gateway, fetcher):
        report = run_discovery(db, gateway, fetcher, uuid.UUID(report_id))
        status = report.status
        if status != "DONE":
            progress.finish(
                "WAITING" if status in ("WAITING_QUOTA", "STOPPED") else "FAILED",
                str(report.params.get("result", {}).get("error") or f"Discovery ended as {status}."),
            )
    log.info("research.discover", report_id=report_id, status=status)
    return status


def blueprint(candidate_id: str, owner_notes: str = "") -> str:
    """research.blueprint: A07 + A06 → blueprint DRAFT for a shortlisted candidate."""
    from tubeforge_agents.discovery import PipelineError, generate_blueprint

    with _tracked("research.blueprint", candidate_id=candidate_id), _research() as (db, gateway, _fetcher):
        try:
            result = generate_blueprint(db, gateway, uuid.UUID(candidate_id), owner_notes=owner_notes)
        except PipelineError as exc:
            _stopped(exc)
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


def _art_failed(db: Session, channel_id: str, title: str, message: str) -> str:
    progress.finish("FAILED", message)
    notify_owners(
        db,
        event_type="media.channel_art_failed",
        severity="WARNING",
        title=title,
        body=message[:300],
        dedup_key=f"channel-art:{channel_id}:{message[:40]}",
        link=f"/channels/{channel_id}/onboarding",
    )
    db.commit()
    return "FAILED"


def channel_art(channel_id: str, tagline: str | None = None) -> str:
    """media.channel_art: 3 logos and 3 banners from the channel's blueprint (Phase 8, owner request)."""
    from tubeforge_media.channel_art import ArtError, generate_channel_art

    data_dir = get_settings().resolved_data_dir
    with _tracked("media.channel_art", channel_id=channel_id), _deps() as (db, *_):
        try:
            rows = generate_channel_art(db, data_dir, uuid.UUID(channel_id), tagline=tagline)
        except ArtError as exc:
            db.rollback()
            return _art_failed(db, channel_id, "Channel art could not be made", str(exc))
        db.commit()
    log.info("media.channel_art", channel_id=channel_id, files=len(rows))
    return f"{len(rows)} files"


def watermark(channel_id: str, source_asset_id: str) -> str:
    """media.watermark: the 150 × 150 video watermark from the owner's uploaded brand logo."""
    from tubeforge_media.channel_art import ArtError, make_watermark

    data_dir = get_settings().resolved_data_dir
    with _tracked("media.watermark", channel_id=channel_id), _deps() as (db, *_):
        try:
            make_watermark(db, data_dir, uuid.UUID(channel_id), uuid.UUID(source_asset_id))
        except ArtError as exc:
            db.rollback()
            return _art_failed(db, channel_id, "The video watermark could not be made", str(exc))
        db.commit()
    log.info("media.watermark", channel_id=channel_id)
    return "watermark ready"


def keywords(channel_id: str, seeds: list[str]) -> int:
    """research.keywords: A05 keyword suggestions for one channel."""
    from tubeforge_agents.discovery import run_keywords

    with _research() as (db, gateway, _fetcher):
        return len(run_keywords(db, gateway, uuid.UUID(channel_id), seeds))


def trend_scan_one(channel_id: str) -> int:
    """research.trend_scan: the owner pressed "Scan now" for one channel."""
    from tubeforge_agents.discovery import run_trend_scan

    with _research() as (db, gateway, fetcher):
        return len(run_trend_scan(db, gateway, fetcher, uuid.UUID(channel_id)))


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


def _content_failed(db: Session, kind: str, subject_id: str, link: str, exc: Any) -> str:
    """A content job could not finish: tell the owner why (quota waits and stops are not failures)."""
    _stopped(exc)
    titles = {
        "ideas": "New ideas could not be generated",
        "research": "The research brief could not be made",
        "script": "The script draft could not be made",
    }
    notify_owners(
        db,
        event_type=f"content.{kind}_failed",
        severity="INFO" if exc.status in ("WAITING_QUOTA", "STOPPED") else "WARNING",
        title=titles[kind],
        body=(
            exc.message[:240]
            + {
                "research": " — Open the project and press Research again.",
                "script": " — Open the project and press Write again.",
            }.get(kind, "")
        )[:300],
        dedup_key=f"content:{kind}:{subject_id}:{exc.status}",
        link=link,
    )
    db.commit()
    log.info(f"content.{kind}", subject_id=subject_id, status=exc.status)
    return str(exc.status)


def content_ideas(
    channel_id: str,
    count: int = 10,
    fmt: str | None = None,
    pillar: str | None = None,
    variation: dict[str, str] | None = None,
) -> str:
    """content.ideas: A08 ideas for one channel (variation = the owner's own video to vary)."""
    from tubeforge_agents.content import Variation, generate_ideas
    from tubeforge_agents.discovery import PipelineError

    with _tracked("content.ideas", channel_id=channel_id), _research() as (db, gateway, _fetcher):
        try:
            result = generate_ideas(
                db,
                gateway,
                uuid.UUID(channel_id),
                count=count,
                fmt=fmt,
                pillar=pillar,
                variation=Variation(**variation) if variation else None,
            )
        except PipelineError as exc:
            return _content_failed(db, "ideas", channel_id, "/ideas", exc)
    status = f"{len(result.ideas)} ideas ({len(result.dropped)} dropped, {result.method})"
    log.info("content.ideas", channel_id=channel_id, status=status)
    return status


def content_research(project_id: str, extra_queries: list[str] | None = None) -> str:
    """content.research: Wikipedia articles → A09 brief → A10 → RESEARCH_REVIEW."""
    from tubeforge_agents.content import run_research
    from tubeforge_agents.discovery import PipelineError

    with _tracked("content.research", project_id=project_id), _research() as (db, gateway, fetcher):
        try:
            result = run_research(
                db, gateway, fetcher, uuid.UUID(project_id), extra_queries=extra_queries or []
            )
        except PipelineError as exc:
            return _content_failed(db, "research", project_id, f"/projects/{project_id}/script", exc)
    log.info("content.research", project_id=project_id, brief=str(result.brief.id))
    return f"brief v{result.brief.version}"


def content_script(project_id: str, instruction: str = "") -> str:
    """content.script: A11 draft (with the owner's instruction, if any) + craft checks (one repair)
    → A10 → SCRIPT_REVIEW."""
    from tubeforge_agents.content import run_script
    from tubeforge_agents.discovery import PipelineError

    with _tracked("content.script", project_id=project_id), _research() as (db, gateway, _fetcher):
        try:
            result = run_script(db, gateway, uuid.UUID(project_id), instruction=instruction)
        except PipelineError as exc:
            return _content_failed(db, "script", project_id, f"/projects/{project_id}/script", exc)
    log.info("content.script", project_id=project_id, version=result.version.version)
    return f"script v{result.version.version} ({len(result.findings)} findings)"


def content_fact_check(version_id: str) -> str:
    """content.fact_check: A10 on one script version (after the owner edits the script)."""
    from tubeforge_agents.content import fact_check_version
    from tubeforge_agents.discovery import PipelineError

    with _tracked("content.fact_check", version_id=version_id), _research() as (db, gateway, _fetcher):
        try:
            found = fact_check_version(db, gateway, uuid.UUID(version_id))
        except PipelineError as exc:
            return _content_failed(db, "script", version_id, "/projects", exc)
    log.info("content.fact_check", version_id=version_id, claims=found)
    return f"{found} claims"


def upload(upload_job_id: str) -> str:
    """yt.upload: run or resume one upload job (Phase 4: private test uploads only)."""
    with _deps() as (db, box, google, youtube):
        job = uploads.run_upload_job(db, box, google, youtube, uuid.UUID(upload_job_id))
        state = job.state
    log.info("yt.upload", upload_job_id=upload_job_id, state=state)
    return state
