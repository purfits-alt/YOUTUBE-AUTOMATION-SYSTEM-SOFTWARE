"""Resumable upload engine (YOUTUBE_API_INTEGRATION §6) and the Phase 4 private test upload.

Protocol (Google resumable uploads, ADR-0026):
1. ``POST /upload/youtube/v3/videos?uploadType=resumable&part=snippet,status`` with the metadata →
   ``Location`` = session URI. This is the one metered ``videos.insert`` call.
2. ``PUT`` the file in chunks (multiples of 256 KiB, default 8 MiB) with ``Content-Range``.
   ``308`` + ``Range: bytes=0-N`` = keep going from N+1; ``200``/``201`` = done (video resource).
3. After a network or 5xx error: ``PUT`` with ``Content-Range: bytes */total`` asks for the offset.

The session URI (encrypted) and the confirmed offset are committed after every step, so a worker
restart resumes where it stopped and a re-run of a finished job never uploads again.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge import channel_lifecycle as lifecycle
from tubeforge.audit import SYSTEM, Actor, record
from tubeforge.db.ids import uuid7
from tubeforge.db.models import (
    ApprovalRequest,
    AssetRights,
    Channel,
    MediaAsset,
    QuotaReservation,
    UploadJob,
    VideoProject,
)
from tubeforge.notifications import notify_owners
from tubeforge.secrets import SecretBox, aad
from tubeforge.youtube import oauth
from tubeforge.youtube.client import UPLOAD_BASE, CallContext, SafeYouTubeClient, UploadIntent, preflight
from tubeforge.youtube.errors import ErrorClass, YouTubeApiError

CHUNK_SIZE = 8 * 1024 * 1024
CHUNK_ALIGN = 256 * 1024
MAX_RESUMES = 8
TEST_CLIP = Path(__file__).parent / "assets" / "test_clip.mp4"
TEST_TITLE = "TubeForge test upload (private)"
TEST_DESCRIPTION = "Private 5-second connection test made by TubeForge. Safe to delete."
FINAL_STATES = ("COMPLETED", "FAILED", "REJECTED", "PROCESSING_FAILED")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def upload_subject_sha256(file_sha256: str, choices: dict[str, Any]) -> str:
    """I-5 binding: the approval covers exactly this file and these choices (SEO/thumbnail in Phase 10)."""
    canonical = json.dumps({"file": file_sha256, "choices": choices}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


# ------------------------------------------------------------------------------------- protocol
@dataclass(frozen=True)
class ChunkResult:
    offset: int  # bytes Google has confirmed
    video: dict[str, Any] | None  # the video resource once the upload is complete


class ResumableUploader:
    def __init__(self, youtube: SafeYouTubeClient) -> None:
        self.youtube = youtube

    def start_session(self, ctx: CallContext, metadata: dict[str, Any], size: int, mime: str) -> str:
        resp = self.youtube.request(
            ctx,
            "videos.insert",
            "POST",
            f"{UPLOAD_BASE}/videos",
            params={"uploadType": "resumable", "part": "snippet,status"},
            json=metadata,
            headers={"X-Upload-Content-Length": str(size), "X-Upload-Content-Type": mime},
        )
        location = resp.headers.get("Location")
        if not location:
            raise YouTubeApiError(
                ErrorClass.UNKNOWN, resp.status_code, None, "no upload session URI returned"
            )
        return str(location)

    @staticmethod
    def _result(resp_status: int, headers: Any, body: bytes) -> ChunkResult:
        if resp_status in (200, 201):
            return ChunkResult(offset=-1, video=json.loads(body))
        rng = headers.get("Range")  # "bytes=0-524287"
        return ChunkResult(offset=int(rng.rsplit("-", 1)[1]) + 1 if rng else 0, video=None)

    def put_chunk(self, ctx: CallContext, uri: str, data: bytes, start: int, total: int) -> ChunkResult:
        end = start + len(data) - 1
        resp = self.youtube.request(
            ctx,
            "videos.insert",
            "PUT",
            uri,
            content=data,
            headers={"Content-Range": f"bytes {start}-{end}/{total}", "Content-Type": "video/mp4"},
            metered=False,
            ok_statuses=(308,),
        )
        return self._result(resp.status_code, resp.headers, resp.content)

    def query_offset(self, ctx: CallContext, uri: str, total: int) -> ChunkResult:
        resp = self.youtube.request(
            ctx,
            "videos.insert",
            "PUT",
            uri,
            content=b"",
            headers={"Content-Range": f"bytes */{total}"},
            metered=False,
            ok_statuses=(308,),
        )
        return self._result(resp.status_code, resp.headers, resp.content)


# ------------------------------------------------------------------------------- test uploads
TEST_CHOICES: dict[str, Any] = {
    "privacy_status": "private",
    "made_for_kids": False,
    "contains_synthetic_media": False,
}


def create_test_upload(
    db: Session, *, channel: Channel, owner: Actor, owner_id: uuid.UUID, now: datetime | None = None
) -> UploadJob:
    """The owner pressed "Test private upload": project + asset + rights + approval + job, then preflight.

    The owner's click is the express consent for this one private insert (DP-6); the approval row
    records it and binds it to the exact file and choices (I-5). Raises PreflightRefused.
    """
    now = now or datetime.now(UTC)
    file_sha, size = sha256_file(TEST_CLIP), TEST_CLIP.stat().st_size
    project = VideoProject(
        id=uuid7(),
        channel_id=channel.id,
        format="LONG",
        state="APPROVED",
        working_title=TEST_TITLE,
        target_duration_s=5,
        render_profile={"width": 640, "height": 360, "fps": 25, "test": True},
        is_test=True,
    )
    asset = MediaAsset(
        id=uuid7(),
        channel_id=channel.id,
        project_id=project.id,
        kind="RENDER_FINAL",
        mime_type="video/mp4",
        size_bytes=size,
        sha256=file_sha,
        width=640,
        height=360,
        duration_s=5,
        origin="PROCEDURAL",
        retention_class="CACHE",
        created_by_type="SYSTEM",
        created_by_id="system",
    )
    db.add(project)
    db.flush()  # media_assets.project_id references the project
    db.add(asset)
    db.flush()
    db.add(
        AssetRights(
            asset_id=asset.id,
            rights_basis="SYSTEM_GENERATED",
            licence_name="TubeForge own test artwork",
            commercial_use_allowed=True,
            lineage={"source": "tubeforge/youtube/assets/test_clip.mp4"},
        )
    )
    subject = upload_subject_sha256(file_sha, TEST_CHOICES)
    approval = ApprovalRequest(
        id=uuid7(),
        channel_id=channel.id,
        subject_type="UPLOAD_PACKAGE",
        subject_id=project.id,
        subject_sha256=subject,
        state="APPROVED",
        requested_by_type=owner.type,
        decided_by=owner_id,
        decided_at=now,
        comment="Owner pressed Test private upload",
        payload=TEST_CHOICES,
        expires_at=now + timedelta(days=1),
    )
    db.add(approval)
    db.flush()
    job_id = uuid7()
    cleared = preflight(
        db,
        UploadIntent(
            channel_id=channel.id,
            project_id=project.id,
            file_sha256=file_sha,
            approval_request_id=approval.id,
            subject_sha256=subject,
            format="LONG",
            privacy_status="private",
            made_for_kids=False,
            contains_synthetic_media=False,
            is_test=True,
            job_id=str(job_id),
        ),
        gcp_project=oauth.gcp_project(oauth.client_for(db, channel.id)),
        now=now,
        actor=owner,
    )
    if cleared.existing is not None:
        return cleared.existing
    job = UploadJob(
        id=job_id,
        project_id=project.id,
        channel_id=channel.id,
        approval_request_id=approval.id,
        file_asset_id=asset.id,
        file_sha256=file_sha,
        state="PREFLIGHT",
        privacy_status="private",
        made_for_kids=False,
        contains_synthetic_media=False,
        bytes_total=size,
        is_test=True,
        steps={},
        created_at=now,
    )
    db.add(job)
    project.state = "UPLOADING"
    record(
        db,
        actor=owner,
        action="upload.test_requested",
        entity_type="upload_job",
        entity_id=str(job.id),
        channel_id=channel.id,
        details={"privacy": "private", "is_test": True, "bytes": size},
    )
    db.flush()
    return job


# ------------------------------------------------------------------------------------- runner
def _metadata(job: UploadJob, project: VideoProject) -> dict[str, Any]:
    # ADR-0016: the three status fields are always sent explicitly, from the approved job row.
    return {
        "snippet": {"title": project.working_title, "description": TEST_DESCRIPTION, "categoryId": "22"},
        "status": {
            "privacyStatus": job.privacy_status,
            "selfDeclaredMadeForKids": job.made_for_kids,
            "containsSyntheticMedia": job.contains_synthetic_media,
        },
    }


def _seal_uri(box: SecretBox, job: UploadJob, uri: str) -> None:
    sealed = box.seal(
        uri.encode(), purpose="upload-session", associated=aad("upload_jobs", "session_uri_enc", job.id)
    )
    job.session_uri_enc, job.key_id = sealed.ciphertext, sealed.key_id


def _open_uri(box: SecretBox, job: UploadJob) -> str:
    assert job.session_uri_enc is not None and job.key_id is not None
    return box.open(
        job.session_uri_enc,
        key_id=job.key_id,
        purpose="upload-session",
        associated=aad("upload_jobs", "session_uri_enc", job.id),
    ).decode()


def _fail(db: Session, job: UploadJob, cls: ErrorClass | str, detail: str) -> UploadJob:
    job.state = "FAILED"
    job.error_class = str(cls)
    job.error_detail = detail[:1000]
    job.session_uri_enc = None
    project = db.get(VideoProject, job.project_id)
    if project is not None:
        project.state = "FAILED"
    for res in db.scalars(
        select(QuotaReservation).where(
            QuotaReservation.job_id == str(job.id), QuotaReservation.state == "HELD"
        )
    ):
        res.state = "RELEASED"
    record(
        db,
        actor=SYSTEM,
        action="upload.failed",
        entity_type="upload_job",
        entity_id=str(job.id),
        channel_id=job.channel_id,
        details={"error_class": str(cls), "detail": detail[:200]},
    )
    notify_owners(
        db,
        event_type="upload.failed",
        severity="WARNING",
        title="Test upload failed" if job.is_test else "Upload failed",
        body=f"{cls}: {detail[:200]}",
        dedup_key=f"upload.failed:{job.id}",
        channel_id=job.channel_id,
        link=f"/channels/{job.channel_id}",
        entity_type="upload_job",
        entity_id=job.id,
    )
    db.commit()
    return job


def _finish(db: Session, job: UploadJob, video: dict[str, Any]) -> UploadJob:
    video_id = str(video["id"])
    job.youtube_video_id = video_id
    job.processing_status = (video.get("status") or {}).get("uploadStatus")
    job.bytes_confirmed = job.bytes_total
    job.session_uri_enc = None
    job.state = "COMPLETED"  # a test upload has no thumbnail/caption/playlist steps
    project = db.get_one(VideoProject, job.project_id)
    project.youtube_video_id = video_id
    project.state = "PRIVATE_DONE"
    channel = db.get_one(Channel, job.channel_id)
    if job.is_test:
        channel.successful_private_test_uploads += 1
        lifecycle.mark_step(db, channel.id, "TEST_UPLOAD")
        lifecycle.maybe_activate(db, channel, actor=SYSTEM)
    record(
        db,
        actor=SYSTEM,
        action="upload.completed",
        entity_type="upload_job",
        entity_id=str(job.id),
        channel_id=channel.id,
        details={"youtube_video_id": video_id, "privacy": job.privacy_status, "is_test": job.is_test},
    )
    notify_owners(
        db,
        event_type="upload.completed",
        severity="INFO",
        title="Private test upload done" if job.is_test else "Upload done",
        body=f"Video {video_id} is on YouTube as {job.privacy_status}. Check it in YouTube Studio.",
        dedup_key=f"upload.completed:{job.id}",
        channel_id=channel.id,
        link=f"/channels/{channel.id}",
        entity_type="upload_job",
        entity_id=job.id,
    )
    db.commit()
    return job


def run_upload_job(
    db: Session,
    box: SecretBox,
    google: oauth.GoogleOAuth,
    youtube: SafeYouTubeClient,
    job_id: uuid.UUID,
    *,
    file_path: Path | None = None,
    chunk_size: int = CHUNK_SIZE,
    sleep: Callable[[float], None] = time.sleep,
    max_resumes: int = MAX_RESUMES,
) -> UploadJob:
    """Run (or resume) one upload job to the end. Safe to call again: finished jobs return at once."""
    if chunk_size % CHUNK_ALIGN:
        raise ValueError("chunk size must be a multiple of 256 KiB")
    job = db.get_one(UploadJob, job_id, with_for_update=True)
    if job.state in FINAL_STATES:
        db.commit()
        return job
    path = file_path or TEST_CLIP
    if not job.is_test and file_path is None:
        return _fail(db, job, "POLICY", "only test uploads are enabled in this version")
    if sha256_file(path) != job.file_sha256 or path.stat().st_size != job.bytes_total:
        return _fail(db, job, ErrorClass.INVALID_REQUEST, "the file changed after approval")
    channel = db.get_one(Channel, job.channel_id)
    project = db.get_one(VideoProject, job.project_id)
    uploader = ResumableUploader(youtube)
    try:
        ctx = oauth.call_context(db, box, google, channel, job_id=str(job.id))
    except (YouTubeApiError, oauth.OAuthFlowError) as exc:
        detail = exc.detail if isinstance(exc, YouTubeApiError) else exc.message
        return _fail(db, job, ErrorClass.AUTH_EXPIRED, detail)
    ctx.reservation = db.scalar(
        select(QuotaReservation).where(
            QuotaReservation.job_id == str(job.id),
            QuotaReservation.bucket == "VIDEO_UPLOADS",
            QuotaReservation.state == "HELD",
        )
    )
    job.attempt += 1

    if job.session_uri_enc is None:
        try:
            uri = uploader.start_session(ctx, _metadata(job, project), job.bytes_total, "video/mp4")
        except YouTubeApiError as exc:
            return _fail(db, job, exc.error_class, exc.detail)
        _seal_uri(box, job, uri)
        job.session_started_at = datetime.now(UTC)
        job.state = "SESSION_STARTED"
        db.commit()
    else:
        uri = _open_uri(box, job)
        job.state = "RESUMING"
        db.commit()
        try:
            status = uploader.query_offset(ctx, uri, job.bytes_total)
        except YouTubeApiError as exc:
            if exc.status in (404, 410):
                # The session expired. A duplicate guard via the uploads playlist arrives with real
                # uploads (Phase 10); a test upload simply fails and the owner can run a new one.
                return _fail(db, job, ErrorClass.TRANSIENT, "upload session expired")
            return _fail(db, job, exc.error_class, exc.detail)
        if status.video is not None:
            return _finish(db, job, status.video)
        job.bytes_confirmed = status.offset
        db.commit()

    resumes = 0
    with path.open("rb") as f:
        while True:
            start = job.bytes_confirmed
            f.seek(start)
            data = f.read(chunk_size)
            job.state = "TRANSFERRING"
            try:
                result = uploader.put_chunk(ctx, uri, data, start, job.bytes_total)
            except YouTubeApiError as exc:
                if not exc.retryable or resumes >= max_resumes:
                    return _fail(db, job, exc.error_class, exc.detail)
                resumes += 1
                job.state = "RESUMING"
                db.commit()
                sleep(5.0 * 2**resumes)
                try:
                    result = uploader.query_offset(ctx, uri, job.bytes_total)
                except YouTubeApiError as again:
                    if not again.retryable:
                        return _fail(db, job, again.error_class, again.detail)
                    continue  # count it as another resume on the next round
            if result.video is not None:
                return _finish(db, job, result.video)
            job.bytes_confirmed = result.offset
            db.commit()
