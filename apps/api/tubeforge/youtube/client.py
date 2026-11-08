"""SafeYouTubeClient — the only code that calls YouTube mutation methods (YOUTUBE_API_INTEGRATION §5).

Every upload goes through :func:`preflight`, which checks invariants I-1…I-12 in order and either
refuses (``PreflightRefused`` with a stable code, recorded in audit_log + security_events +
a notification) or returns a :class:`Cleared` ticket holding the quota reservations.

Phase 4 scope: only **private test uploads** to a CONNECTED/ACTIVE channel pass. Non-test uploads are
refused at I-4 until the auditors exist (Phase 9); the auto-publish rule check (I-12) refuses until
Phase 14. HTTP goes through httpx with an injectable transport so tests never touch Google (ADR-0026).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tubeforge.audit import SYSTEM, Actor, record, security_event
from tubeforge.db.models import (
    ApprovalRequest,
    Channel,
    ChannelPublishingRules,
    KillSwitch,
    OAuthConnection,
    QuotaReservation,
    SystemSettings,
    UploadJob,
    VideoProject,
)
from tubeforge.notifications import notify_owners
from tubeforge.youtube import quota
from tubeforge.youtube.errors import ErrorClass, YouTubeApiError, from_response

API_BASE = "https://www.googleapis.com/youtube/v3"
UPLOAD_BASE = "https://www.googleapis.com/upload/youtube/v3"
# The only hosts this module talks to (network allowlist, SYSTEM_ARCHITECTURE §11).
ALLOWED_HOSTS = frozenset({"www.googleapis.com", "youtube.googleapis.com"})
SCHEDULE_MIN_LEAD = timedelta(minutes=15)
UPLOADABLE_STATES = {"CONNECTED", "ACTIVE"}
CLOSED_JOB_STATES = ("FAILED", "REJECTED")


class PreflightRefused(Exception):  # noqa: N818 - the codes are REFUSED_*
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class UploadIntent:
    """What the caller wants to upload. ``None`` in the three status fields = not decided (I-6)."""

    channel_id: uuid.UUID
    project_id: uuid.UUID
    file_sha256: str
    approval_request_id: uuid.UUID
    subject_sha256: str
    format: str  # LONG | SHORT
    privacy_status: str | None
    made_for_kids: bool | None
    contains_synthetic_media: bool | None
    publish_at: datetime | None = None
    is_test: bool = False
    previously_published: bool = False
    job_id: str | None = None


@dataclass
class Cleared:
    """Preflight passed. ``existing`` is set when I-11 found the same upload already in progress/done."""

    reservations: list[QuotaReservation] = field(default_factory=list)
    existing: UploadJob | None = None
    gcp_project: str = quota.DEFAULT_PROJECT


def _refuse(db: Session, intent: UploadIntent, code: str, message: str, actor: Actor) -> PreflightRefused:
    record(
        db,
        actor=actor,
        action="youtube.preflight_refused",
        entity_type="video_project",
        entity_id=str(intent.project_id),
        channel_id=intent.channel_id,
        details={"code": code, "message": message, "is_test": intent.is_test},
    )
    security_event(
        db, "YOUTUBE_PREFLIGHT_REFUSED", "WARNING", channel_id=intent.channel_id, details={"code": code}
    )
    notify_owners(
        db,
        event_type="upload.refused",
        severity="WARNING",
        title="Upload stopped by a safety check",
        body=message,
        dedup_key=f"preflight:{intent.project_id}:{code}",
        channel_id=intent.channel_id,
        link=f"/channels/{intent.channel_id}",
        entity_type="video_project",
        entity_id=intent.project_id,
    )
    return PreflightRefused(code, message)


def _uploads_since(db: Session, channel_id: uuid.UUID, since: datetime, fmt: str | None) -> int:
    q = (
        select(func.count())
        .select_from(UploadJob)
        .join(VideoProject, VideoProject.id == UploadJob.project_id)
        .where(
            UploadJob.channel_id == channel_id,
            UploadJob.is_test.is_(False),
            UploadJob.state.not_in(CLOSED_JOB_STATES),
            UploadJob.created_at >= since,
        )
    )
    if fmt is not None:
        q = q.where(VideoProject.format == fmt)
    return int(db.scalar(q) or 0)


def _audits_pass(db: Session, intent: UploadIntent) -> bool:
    """I-4. Phase 9 reads audit_reports/audit_overrides for ``intent.subject_sha256``; until then, no."""
    return False


def preflight(
    db: Session,
    intent: UploadIntent,
    *,
    gcp_project: str = quota.DEFAULT_PROJECT,
    now: datetime | None = None,
    actor: Actor = SYSTEM,
) -> Cleared:
    """Check I-1…I-12 for one upload. Runs in the caller's transaction; refusals are recorded there."""
    now = now or datetime.now(UTC)

    def refuse(code: str, message: str) -> PreflightRefused:
        return _refuse(db, intent, code, message, actor)

    settings = db.get(SystemSettings, 1)
    # I-1 Emergency Stop
    if settings is None or settings.emergency_stop:
        raise refuse("REFUSED_EMERGENCY_STOP", "Emergency Stop is on. Nothing is sent to YouTube.")

    # I-2 kill switches (channel; publishing for public/scheduled)
    publishing = intent.privacy_status in ("public", "unlisted") or intent.publish_at is not None
    scopes = ["CHANNEL"] + (["PUBLISHING_CHANNEL"] if publishing else [])
    switch = db.scalar(
        select(KillSwitch.id).where(
            KillSwitch.active.is_(True),
            KillSwitch.scope.in_(scopes),
            KillSwitch.target_id == str(intent.channel_id),
        )
    )
    if switch is not None or (publishing and settings.publishing_kill_switch):
        raise refuse("REFUSED_KILL_SWITCH", "A kill switch is on for this channel or for publishing.")

    # I-3 channel state + token health
    channel = db.get(Channel, intent.channel_id)
    if channel is None or channel.deleted_at is not None or channel.state not in UPLOADABLE_STATES:
        state = channel.state if channel else "MISSING"
        raise refuse("REFUSED_CHANNEL_STATE", f"The channel is {state}; it must be connected.")
    if channel.state == "CONNECTED" and not intent.is_test:
        raise refuse("REFUSED_CHANNEL_STATE", "A newly connected channel can only receive test uploads.")
    connection = db.scalar(
        select(OAuthConnection)
        .where(OAuthConnection.channel_id == channel.id, OAuthConnection.revoked_at.is_(None))
        .order_by(OAuthConnection.created_at.desc())
        .limit(1)
    )
    if connection is None or connection.status != "ACTIVE":
        raise refuse("REFUSED_CHANNEL_STATE", "The YouTube connection needs to be renewed.")

    # I-4 audits — auditors arrive in Phase 9, so only test uploads pass for now.
    if not intent.is_test and not _audits_pass(db, intent):
        raise refuse("REFUSED_AUDIT", "Quality and copyright audits are not available yet (Phase 9).")

    # I-5 approval bound to exactly this content
    approval = db.get(ApprovalRequest, intent.approval_request_id)
    if (
        approval is None
        or approval.state != "APPROVED"
        or approval.channel_id != intent.channel_id
        or approval.subject_sha256 != intent.subject_sha256
        or approval.expires_at <= now
    ):
        raise refuse("REFUSED_APPROVAL", "This exact upload has not been approved by the owner.")

    # I-6 explicit status fields (ADR-0016)
    if (
        intent.privacy_status is None
        or intent.made_for_kids is None
        or intent.contains_synthetic_media is None
    ):
        raise refuse(
            "REFUSED_IMPLICIT_FIELD",
            "Privacy, made-for-kids and synthetic-media must each be chosen explicitly.",
        )
    if intent.privacy_status not in ("private", "unlisted", "public"):
        raise refuse("REFUSED_IMPLICIT_FIELD", "Unknown privacy status.")
    if intent.is_test and (intent.privacy_status != "private" or intent.publish_at is not None):
        raise refuse("REFUSED_PRIVATE_ONLY", "Test uploads are always private and never scheduled.")

    # I-7 private-only mode
    if channel.private_only_mode and (intent.privacy_status != "private" or intent.publish_at is not None):
        raise refuse("REFUSED_PRIVATE_ONLY", "Private-only mode is on for this channel.")

    # I-8 schedule rules (Y14)
    if intent.publish_at is not None and (
        intent.privacy_status != "private"
        or intent.publish_at < now + SCHEDULE_MIN_LEAD
        or intent.previously_published
    ):
        raise refuse(
            "REFUSED_SCHEDULE",
            "A scheduled time needs a private, never-published video and must be at least 15 minutes ahead.",
        )

    # I-9 publishing caps (owner timezone); test uploads do not count
    if not intent.is_test:
        rules = db.get(ChannelPublishingRules, channel.id)
        tz = ZoneInfo(settings.owner_timezone)
        local = now.astimezone(tz)
        day_start = datetime.combine(local.date(), datetime.min.time(), tzinfo=tz)
        week_start = day_start - timedelta(days=local.weekday())
        if rules is not None:
            per_day = rules.max_shorts_per_day if intent.format == "SHORT" else rules.max_long_per_day
            if _uploads_since(db, channel.id, day_start, intent.format) >= per_day:
                raise refuse("REFUSED_CAP", "Today's upload cap for this channel is reached.")
            if (
                intent.format == "LONG"
                and _uploads_since(db, channel.id, week_start, "LONG") >= rules.max_long_per_week
            ):
                raise refuse("REFUSED_CAP", "This week's upload cap for this channel is reached.")

    # I-11 idempotency: the same file for the same project is already in progress or done
    existing = db.scalar(
        select(UploadJob).where(
            UploadJob.project_id == intent.project_id,
            UploadJob.file_sha256 == intent.file_sha256,
            UploadJob.state.not_in(CLOSED_JOB_STATES),
        )
    )
    if existing is not None:
        return Cleared(existing=existing, gcp_project=gcp_project)

    # I-12 auto-publish without a human decision
    if approval.decided_by is None:
        rules = db.get(ChannelPublishingRules, channel.id)
        if rules is None or rules.auto_publish_accepted_at is None or approval.auto_rule_id is None:
            raise refuse("REFUSED_AUTO_RULE", "No accepted auto-publish rules cover this upload.")
        raise refuse("REFUSED_AUTO_RULE", "Auto-publish rule checks arrive in Phase 14.")

    # I-10 quota (last, so a refusal above never holds quota)
    try:
        held = [
            quota.reserve(
                db,
                project=gcp_project,
                method="videos.insert",
                purpose="upload",
                job_id=intent.job_id,
                now=now,
            )
        ]
    except quota.QuotaExhausted as exc:
        raise PreflightRefused(
            "WAITING_QUOTA", f"No upload quota left today; it resets at {exc.resets_at.isoformat()}."
        ) from exc
    return Cleared(reservations=held, gcp_project=gcp_project)


# ------------------------------------------------------------------------------------------- HTTP
@dataclass
class CallContext:
    db: Session
    gcp_project: str
    access_token: str
    channel_id: uuid.UUID | None = None
    job_id: str | None = None
    reservation: QuotaReservation | None = None


class SafeYouTubeClient:
    """Thin REST client over httpx. Every request is metered in the quota ledger and classified."""

    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = 60.0) -> None:
        self._http = httpx.Client(transport=transport, timeout=timeout, follow_redirects=False)

    def close(self) -> None:
        self._http.close()

    def request(
        self,
        ctx: CallContext,
        method_name: str,
        verb: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        metered: bool = True,
    ) -> httpx.Response:
        """Send one request. ``metered=False`` only for resumable-upload chunk PUTs (part of one insert)."""
        host = httpx.URL(url).host
        if host not in ALLOWED_HOSTS:
            raise YouTubeApiError(ErrorClass.INVALID_REQUEST, None, None, f"host {host} is not allowed")
        send_headers = {"Authorization": f"Bearer {ctx.access_token}", **(headers or {})}
        try:
            resp = self._http.request(
                verb, url, params=params, json=json, content=content, headers=send_headers
            )
        except httpx.TransportError as exc:
            # The request may or may not have reached Google; meter it (Google bills invalid calls too).
            if metered:
                quota.record_call(
                    ctx.db,
                    project=ctx.gcp_project,
                    method=method_name,
                    reservation=ctx.reservation,
                    channel_id=ctx.channel_id,
                    job_id=ctx.job_id,
                    error_reason=type(exc).__name__,
                )
            raise YouTubeApiError(ErrorClass.TRANSIENT, None, None, type(exc).__name__) from exc
        error = from_response(resp.status_code, resp.content) if resp.status_code >= 400 else None
        if metered:
            quota.record_call(
                ctx.db,
                project=ctx.gcp_project,
                method=method_name,
                reservation=ctx.reservation,
                channel_id=ctx.channel_id,
                job_id=ctx.job_id,
                http_status=resp.status_code,
                error_reason=error.reason if error else None,
            )
        if error is not None:
            if error.error_class is ErrorClass.QUOTA_EXCEEDED:
                quota.exhaust(ctx.db, project=ctx.gcp_project, bucket=quota.bucket_for(method_name))
            raise error
        return resp

    def my_channel(self, ctx: CallContext) -> dict[str, Any]:
        """channels.list mine=true — identity confirmation after OAuth (1 unit)."""
        resp = self.request(
            ctx,
            "channels.list",
            "GET",
            f"{API_BASE}/channels",
            params={"part": "id,snippet", "mine": "true", "maxResults": 1},
        )
        items = resp.json().get("items") or []
        if not items:
            raise YouTubeApiError(ErrorClass.INVALID_REQUEST, 200, "noChannel", "this account has no channel")
        item: dict[str, Any] = items[0]
        return item
