"""YouTube data retention jobs (DATABASE_SCHEMA §15, Developer Policies DP-2/3/4).

- ``purge_api_cache`` (hourly): owner-lookup cache rows past ``expires_at`` (≤ 30 days, DP-2).
- ``purge_pending_flows`` (10 min): expired PKCE rows.
- ``run_deletion_tasks`` (hourly): delete a channel's stored YouTube API data, then close the task;
  a disconnecting channel becomes DISCONNECTED. Overdue tasks raise a CRITICAL alert (DP-4, 7 days).
- ``reauthorize_check`` (daily): every 25 days per connection, confirm the token still belongs to the
  same channel and that stored video IDs still exist; data for removed videos is deleted (DP-3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from tubeforge import channel_lifecycle as lifecycle
from tubeforge.audit import SYSTEM, record
from tubeforge.db.models import (
    Channel,
    DataDeletionTask,
    OAuthConnection,
    OAuthPendingFlow,
    VideoProject,
    YoutubeApiCache,
)
from tubeforge.notifications import notify_owners
from tubeforge.secrets import SecretBox
from tubeforge.youtube import oauth
from tubeforge.youtube.client import API_BASE, SafeYouTubeClient
from tubeforge.youtube.errors import ErrorClass, YouTubeApiError

REAUTH_CHECK_EVERY = timedelta(days=25)
# Tables holding YouTube API data per channel. Fixed allowlist: names never come from task rows.
CHANNEL_DATA_TABLES = ("analytics_snapshots", "comment_suggestions")


def purge_api_cache(db: Session, *, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    n = _rowcount(db.execute(delete(YoutubeApiCache).where(YoutubeApiCache.expires_at < now)))
    db.flush()
    return n


def purge_pending_flows(db: Session, *, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    n = _rowcount(db.execute(delete(OAuthPendingFlow).where(OAuthPendingFlow.expires_at < now)))
    db.flush()
    return n


def _rowcount(result: object) -> int:
    return int(getattr(result, "rowcount", 0) or 0)


def _delete_channel_api_data(db: Session, channel_id: object, video_ids: list[str] | None = None) -> int:
    """All API data of a channel, or (``video_ids``) the analytics of videos that no longer exist."""
    if video_ids is not None:
        return _rowcount(
            db.execute(
                text("DELETE FROM analytics_snapshots WHERE channel_id = :c AND youtube_video_id = ANY(:v)"),
                {"c": channel_id, "v": video_ids},
            )
        )
    total = 0
    for table in CHANNEL_DATA_TABLES:
        sql = f"DELETE FROM {table} WHERE channel_id = :c"  # noqa: S608 - table from a fixed allowlist
        total += _rowcount(db.execute(text(sql), {"c": channel_id}))
    return total


@dataclass
class DeletionResult:
    completed: int = 0
    rows_deleted: int = 0
    overdue: int = 0


def run_deletion_tasks(db: Session, *, now: datetime | None = None) -> DeletionResult:
    now = now or datetime.now(UTC)
    result = DeletionResult()
    tasks = db.scalars(
        select(DataDeletionTask)
        .where(DataDeletionTask.completed_at.is_(None))
        .with_for_update(skip_locked=True)
    ).all()
    for task in tasks:
        try:
            with db.begin_nested():
                rows = 0
                if task.channel_id is not None:
                    rows = _delete_channel_api_data(db, task.channel_id)
                    db.execute(delete(OAuthConnection).where(OAuthConnection.channel_id == task.channel_id))
                    channel = db.get(Channel, task.channel_id)
                    if channel is not None and channel.state == "DISCONNECTING":
                        lifecycle.transition(db, channel, "DISCONNECTED", event="data_deleted", actor=SYSTEM)
                        lifecycle.reset_connection_steps(db, channel)
                task.completed_at = now
                record(
                    db,
                    actor=SYSTEM,
                    action="retention.deletion_completed",
                    entity_type="data_deletion_task",
                    entity_id=str(task.id),
                    channel_id=task.channel_id,
                    details={"reason": task.reason, "rows": rows},
                )
            result.completed += 1
            result.rows_deleted += rows
        except Exception:  # one broken task must not block the others; it stays open and is alerted
            if task.due_at <= now:
                result.overdue += 1
                notify_owners(
                    db,
                    event_type="retention.overdue",
                    severity="CRITICAL",
                    title="YouTube data deletion is overdue",
                    body="A required deletion of stored YouTube data did not finish within 7 days. "
                    "Open the Audit & Security Center.",
                    dedup_key=f"retention.overdue:{task.id}",
                    dedup_window=timedelta(hours=6),
                    channel_id=task.channel_id,
                    now=now,
                )
    db.flush()
    return result


@dataclass
class ReauthResult:
    checked: int = 0
    mismatched: int = 0
    removed_videos: list[str] = field(default_factory=list)
    errors: int = 0


def reauthorize_check(
    db: Session,
    box: SecretBox,
    google: oauth.GoogleOAuth,
    youtube: SafeYouTubeClient,
    *,
    now: datetime | None = None,
) -> ReauthResult:
    now = now or datetime.now(UTC)
    result = ReauthResult()
    due = db.scalars(
        select(OAuthConnection).where(
            OAuthConnection.status == "ACTIVE",
            OAuthConnection.revoked_at.is_(None),
            (OAuthConnection.last_authorization_check_at.is_(None))
            | (OAuthConnection.last_authorization_check_at < now - REAUTH_CHECK_EVERY),
        )
    ).all()
    for conn in due:
        channel = db.get(Channel, conn.channel_id)
        if channel is None:
            continue
        result.checked += 1
        try:
            identity = oauth.fetch_identity(db, box, google, youtube, channel, now=now)
            if channel.youtube_channel_id and identity["youtube_channel_id"] != channel.youtube_channel_id:
                result.mismatched += 1
                oauth.mark_needs_reauth(db, conn, "authorised account no longer matches the channel", now=now)
                continue
            gone = _missing_videos(db, box, google, youtube, channel, now=now)
            if gone:
                _delete_channel_api_data(db, channel.id, gone)
                for project in db.scalars(
                    select(VideoProject).where(
                        VideoProject.channel_id == channel.id, VideoProject.youtube_video_id.in_(gone)
                    )
                ):
                    project.youtube_video_id = None
                result.removed_videos.extend(gone)
            conn.last_authorization_check_at = now
        except YouTubeApiError as exc:
            if exc.error_class is not ErrorClass.AUTH_EXPIRED:
                result.errors += 1
        db.flush()
    return result


def _missing_videos(
    db: Session,
    box: SecretBox,
    google: oauth.GoogleOAuth,
    youtube: SafeYouTubeClient,
    channel: Channel,
    *,
    now: datetime,
) -> list[str]:
    ids = [
        v
        for v in db.scalars(
            select(VideoProject.youtube_video_id).where(
                VideoProject.channel_id == channel.id, VideoProject.youtube_video_id.is_not(None)
            )
        )
        if v
    ]
    if not ids:
        return []
    ctx = oauth.call_context(db, box, google, channel, now=now)
    found: set[str] = set()
    for i in range(0, len(ids), 50):  # videos.list takes up to 50 IDs per call (1 unit)
        batch = ids[i : i + 50]
        resp = youtube.request(
            ctx, "videos.list", "GET", f"{API_BASE}/videos", params={"part": "id", "id": ",".join(batch)}
        )
        found |= {str(item["id"]) for item in resp.json().get("items") or []}
    return sorted(set(ids) - found)
