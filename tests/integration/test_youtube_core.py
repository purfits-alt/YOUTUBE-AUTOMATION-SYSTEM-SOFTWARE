"""SafeYouTubeClient invariants I-1…I-12 (each on its own), quota ledger and the httpx client."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from tests.integration.conftest import Env
from tubeforge.db.ids import uuid7
from tubeforge.db.models import (
    ApprovalRequest,
    AuditLog,
    Channel,
    ChannelPublishingRules,
    KillSwitch,
    MediaAsset,
    Notification,
    OAuthClient,
    OAuthConnection,
    QuotaLedger,
    QuotaReservation,
    SecurityEvent,
    SystemSettings,
    UploadJob,
    VideoProject,
)
from tubeforge.youtube import quota
from tubeforge.youtube.client import CallContext, PreflightRefused, SafeYouTubeClient, UploadIntent, preflight
from tubeforge.youtube.errors import ErrorClass, YouTubeApiError

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
SHA = hashlib.sha256(b"clip").hexdigest()
SUBJECT = hashlib.sha256(b"subject").hexdigest()


@pytest.fixture
def db(env: Env) -> Iterator[Session]:
    engine = create_engine(env.db_url)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def intent(db: Session, env: Env) -> UploadIntent:
    """A connected test channel with a healthy token, a project, a file and an approved test upload."""
    channel = Channel(
        id=uuid7(), name="Test channel", state="CONNECTED", content_language="en", is_test_channel=True
    )
    db.add(channel)
    db.flush()
    client = OAuthClient(id=uuid7(), label="Desktop", client_id="1-abc.apps.googleusercontent.com")
    db.add(client)
    db.flush()
    db.add(
        OAuthConnection(
            id=uuid7(),
            channel_id=channel.id,
            oauth_client_id=client.id,
            scopes=["youtube.upload", "youtube.readonly"],
            refresh_token_enc=b"x",
            key_id="master-key-v1",
            status="ACTIVE",
            authorized_at=NOW,
        )
    )
    db.add(ChannelPublishingRules(channel_id=channel.id, max_long_per_day=1, max_long_per_week=2))
    project = VideoProject(
        id=uuid7(),
        channel_id=channel.id,
        format="LONG",
        state="APPROVED",
        working_title="Test upload",
        target_duration_s=5,
        render_profile={},
        is_test=True,
    )
    asset = MediaAsset(
        id=uuid7(),
        channel_id=channel.id,
        kind="RENDER_FINAL",
        mime_type="video/mp4",
        size_bytes=11861,
        sha256=SHA,
        origin="PROCEDURAL",
        retention_class="MASTER",
        created_by_type="SYSTEM",
        created_by_id="system",
    )
    db.add_all([project, asset])
    db.flush()
    approval = ApprovalRequest(
        id=uuid7(),
        channel_id=channel.id,
        subject_type="UPLOAD_PACKAGE",
        subject_id=project.id,
        subject_sha256=SUBJECT,
        state="APPROVED",
        requested_by_type="USER",
        decided_by=env.owner.id,
        decided_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    db.add(approval)
    db.commit()
    return UploadIntent(
        channel_id=channel.id,
        project_id=project.id,
        file_sha256=SHA,
        approval_request_id=approval.id,
        subject_sha256=SUBJECT,
        format="LONG",
        privacy_status="private",
        made_for_kids=False,
        contains_synthetic_media=False,
        is_test=True,
    )


def refused(db: Session, intent: UploadIntent) -> str:
    with pytest.raises(PreflightRefused) as exc:
        preflight(db, intent, now=NOW)
    return exc.value.code


def test_clean_test_upload_passes_and_reserves_one_upload(db: Session, intent: UploadIntent) -> None:
    cleared = preflight(db, intent, now=NOW)
    assert cleared.existing is None
    [res] = cleared.reservations
    assert (res.bucket, res.units, res.state) == ("VIDEO_UPLOADS", 1, "HELD")


def test_i1_emergency_stop(db: Session, intent: UploadIntent) -> None:
    db.get_one(SystemSettings, 1).emergency_stop = True
    assert refused(db, intent) == "REFUSED_EMERGENCY_STOP"


def test_i2_channel_kill_switch(db: Session, intent: UploadIntent, env: Env) -> None:
    db.add(
        KillSwitch(
            id=uuid7(), scope="CHANNEL", target_id=str(intent.channel_id), reason="t", set_by=env.owner.id
        )
    )
    assert refused(db, intent) == "REFUSED_KILL_SWITCH"


def test_i2_publishing_kill_switch_only_blocks_publishing(db: Session, intent: UploadIntent) -> None:
    db.get_one(SystemSettings, 1).publishing_kill_switch = True
    preflight(db, intent, now=NOW)  # private test upload is not publishing
    public = replace(intent, privacy_status="public", is_test=False)
    assert refused(db, public) == "REFUSED_KILL_SWITCH"


@pytest.mark.parametrize("state", ["APPROVED", "ONBOARDING", "PAUSED", "NEEDS_REAUTH", "DISCONNECTED"])
def test_i3_channel_state(db: Session, intent: UploadIntent, state: str) -> None:
    db.get_one(Channel, intent.channel_id).state = state
    assert refused(db, intent) == "REFUSED_CHANNEL_STATE"


def test_i3_token_health(db: Session, intent: UploadIntent) -> None:
    conn = db.scalars(select(OAuthConnection).where(OAuthConnection.channel_id == intent.channel_id)).one()
    conn.status = "NEEDS_REAUTH"
    assert refused(db, intent) == "REFUSED_CHANNEL_STATE"


def test_i3_connected_channel_takes_test_uploads_only(db: Session, intent: UploadIntent) -> None:
    assert refused(db, replace(intent, is_test=False)) == "REFUSED_CHANNEL_STATE"


def test_i4_non_test_upload_needs_audits(db: Session, intent: UploadIntent) -> None:
    db.get_one(Channel, intent.channel_id).state = "ACTIVE"
    assert refused(db, replace(intent, is_test=False)) == "REFUSED_AUDIT"


@pytest.mark.parametrize("change", ["pending", "hash", "expired"])
def test_i5_approval_must_match(db: Session, intent: UploadIntent, change: str) -> None:
    approval = db.get_one(ApprovalRequest, intent.approval_request_id)
    if change == "pending":
        approval.state = "PENDING"
    elif change == "expired":
        approval.expires_at = NOW - timedelta(seconds=1)
    probe = replace(intent, subject_sha256="0" * 64) if change == "hash" else intent
    assert refused(db, probe) == "REFUSED_APPROVAL"


@pytest.mark.parametrize("field", ["privacy_status", "made_for_kids", "contains_synthetic_media"])
def test_i6_status_fields_are_explicit(db: Session, intent: UploadIntent, field: str) -> None:
    assert refused(db, replace(intent, **{field: None})) == "REFUSED_IMPLICIT_FIELD"


def test_i7_private_only_and_test_uploads_are_private(db: Session, intent: UploadIntent) -> None:
    assert refused(db, replace(intent, privacy_status="unlisted")) == "REFUSED_PRIVATE_ONLY"


def test_i7_private_only_mode_on_active_channel(db: Session, intent: UploadIntent) -> None:
    # Reach I-7 for a non-test upload: I-4 refuses those first, so check the order with a test upload
    # whose channel is in private-only mode and asks for a schedule.
    assert refused(db, replace(intent, publish_at=NOW + timedelta(days=1))) == "REFUSED_PRIVATE_ONLY"


def _past_test_only_checks(db: Session, intent: UploadIntent) -> UploadIntent:
    """Turn off the test-only rules so I-8 / I-9 can be exercised directly."""
    db.get_one(Channel, intent.channel_id).private_only_mode = False
    return intent


def test_i8_schedule_rules(db: Session, intent: UploadIntent, monkeypatch: pytest.MonkeyPatch) -> None:
    import tubeforge.youtube.client as c

    _past_test_only_checks(db, intent)
    # The test-upload privacy rule comes first; check I-8's own logic through a non-test intent
    # with I-4 temporarily satisfied (auditors are Phase 9).
    monkeypatch.setattr(c, "_audits_pass", lambda *_: True)
    soon = replace(intent, is_test=False, publish_at=NOW + timedelta(minutes=5))
    db.get_one(Channel, intent.channel_id).state = "ACTIVE"
    assert refused(db, soon) == "REFUSED_SCHEDULE"
    assert refused(db, replace(soon, publish_at=NOW + timedelta(hours=1), privacy_status="public")) == (
        "REFUSED_SCHEDULE"
    )
    assert refused(db, replace(soon, publish_at=NOW + timedelta(hours=1), previously_published=True)) == (
        "REFUSED_SCHEDULE"
    )


def test_i9_publishing_caps(db: Session, intent: UploadIntent, monkeypatch: pytest.MonkeyPatch) -> None:
    import tubeforge.youtube.client as c

    _past_test_only_checks(db, intent)
    monkeypatch.setattr(c, "_audits_pass", lambda *_: True)
    db.get_one(Channel, intent.channel_id).state = "ACTIVE"
    real = replace(intent, is_test=False)
    _add_job(db, intent, sha="a" * 64, is_test=False, created_at=NOW - timedelta(hours=1))
    assert refused(db, real) == "REFUSED_CAP"


def _add_job(
    db: Session, intent: UploadIntent, *, sha: str, is_test: bool, created_at: datetime
) -> UploadJob:
    asset = db.scalars(select(MediaAsset).where(MediaAsset.channel_id == intent.channel_id)).first()
    assert asset is not None
    job = UploadJob(
        id=uuid7(),
        project_id=intent.project_id,
        channel_id=intent.channel_id,
        approval_request_id=intent.approval_request_id,
        file_asset_id=asset.id,
        file_sha256=sha,
        state="COMPLETED",
        privacy_status="private",
        made_for_kids=False,
        contains_synthetic_media=False,
        bytes_total=1,
        is_test=is_test,
        created_at=created_at,
    )
    db.add(job)
    db.flush()
    return job


def test_i10_quota_exhausted_means_waiting(db: Session, intent: UploadIntent) -> None:
    for _ in range(90):  # 100 calls minus the 10 % reserve
        quota.record_call(db, project="default", method="videos.insert", now=NOW)
    assert refused(db, intent) == "WAITING_QUOTA"


def test_i11_same_file_returns_existing_job(db: Session, intent: UploadIntent) -> None:
    job = _add_job(db, intent, sha=SHA, is_test=True, created_at=NOW)
    cleared = preflight(db, intent, now=NOW)
    assert cleared.existing is not None and cleared.existing.id == job.id
    assert cleared.reservations == []


def test_i12_auto_publish_needs_accepted_rules(db: Session, intent: UploadIntent) -> None:
    approval = db.get_one(ApprovalRequest, intent.approval_request_id)
    approval.decided_by = None
    approval.auto_rule_id = "rule-1"
    assert refused(db, intent) == "REFUSED_AUTO_RULE"


def test_refusal_is_audited_logged_and_notified(db: Session, intent: UploadIntent) -> None:
    db.get_one(SystemSettings, 1).emergency_stop = True
    assert refused(db, intent) == "REFUSED_EMERGENCY_STOP"
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "youtube.preflight_refused")).one()
    assert audit.details["code"] == "REFUSED_EMERGENCY_STOP"
    assert db.scalar(
        select(func.count()).select_from(SecurityEvent).where(SecurityEvent.severity == "WARNING")
    )
    note = db.scalars(select(Notification)).one()
    assert note.event_type == "UPLOAD_REFUSED" and note.channel_id == intent.channel_id


# ------------------------------------------------------------------------------------------ quota
def test_research_share_limits_search(db: Session, env: Env) -> None:
    for _ in range(30):
        res = quota.reserve(db, project="default", method="search.list", purpose="research", now=NOW)
        quota.record_call(db, project="default", method="search.list", reservation=res, now=NOW)
    with pytest.raises(quota.QuotaExhausted):
        quota.reserve(db, project="default", method="search.list", purpose="research", now=NOW)
    quota.reserve(db, project="default", method="search.list", purpose="owner-lookup", now=NOW)


def test_expired_and_released_reservations_free_quota(db: Session, env: Env) -> None:
    res = quota.reserve(db, project="default", method="videos.insert", calls=90, purpose="t", now=NOW)
    with pytest.raises(quota.QuotaExhausted):
        quota.reserve(db, project="default", method="videos.insert", purpose="t", now=NOW)
    quota.reserve(db, project="default", method="videos.insert", purpose="t", now=NOW + timedelta(minutes=31))
    quota.release(db, res)
    assert res.state == "RELEASED"
    quota.reserve(db, project="default", method="videos.insert", purpose="t", now=NOW)


def test_unknown_method_cost_is_a_config_error(db: Session, env: Env) -> None:
    with pytest.raises(quota.QuotaError):
        quota.reserve(db, project="default", method="videos.delete", purpose="t", now=NOW)
    with pytest.raises(quota.QuotaError):  # ANALYTICS has no default: the owner enters it
        quota.reserve(db, project="default", method="youtubeAnalytics.reports.query", purpose="t", now=NOW)


def test_status_and_forecast(db: Session, env: Env) -> None:
    quota.record_call(db, project="my-proj", method="thumbnails.set", now=NOW)
    by_bucket = {s.bucket: s for s in quota.status(db, "my-proj", now=NOW)}
    assert by_bucket["DEFAULT"].used == 50 and by_bucket["DEFAULT"].usable == 9000
    assert by_bucket["VIDEO_UPLOADS"].available == 90
    assert by_bucket["DEFAULT"].resets_at_pkt == "13:00 PKT"
    assert quota.package_cost(db, "default") == 550
    day = quota.pt_day(NOW)
    [ok, too_many] = quota.forecast(db, "default", {day: 10, day + timedelta(days=1): 17})
    assert ok.ok and not too_many.ok  # 17 × 550 = 9,350 > 9,000 usable


def test_concurrent_reservations_never_oversell(env: Env) -> None:
    """20 workers race for the last 5 upload calls; exactly 5 win."""
    engine = create_engine(env.db_url, pool_size=25)
    with Session(engine) as setup:
        quota.reserve(setup, project="race", method="videos.insert", calls=85, purpose="fill", now=NOW)
        setup.commit()
    wins: list[int] = []
    barrier = threading.Barrier(20)

    def worker() -> None:
        with Session(engine) as s:
            barrier.wait()
            try:
                quota.reserve(s, project="race", method="videos.insert", purpose="race", now=NOW)
                s.commit()
                wins.append(1)
            except quota.QuotaExhausted:
                s.rollback()

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with Session(engine) as s:
        held = s.scalar(
            select(func.sum(QuotaReservation.units)).where(
                QuotaReservation.gcp_project == "race", QuotaReservation.state == "HELD"
            )
        )
    engine.dispose()
    assert len(wins) == 5 and held == 90


# ------------------------------------------------------------------------------------------- HTTP
def _client(handler: httpx.MockTransport) -> SafeYouTubeClient:
    return SafeYouTubeClient(transport=handler)


def test_http_call_is_metered_and_identity_read(db: Session, env: Env) -> None:
    seen: list[httpx.Request] = []

    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"items": [{"id": "UC123", "snippet": {"title": "Mine"}}]})

    yt = _client(httpx.MockTransport(handle))
    item = yt.my_channel(CallContext(db=db, gcp_project="default", access_token="tok"))
    assert item["id"] == "UC123"
    assert seen[0].headers["Authorization"] == "Bearer tok"
    assert seen[0].url.params["mine"] == "true"
    row = db.scalars(select(QuotaLedger)).one()
    assert (row.method, row.units, row.http_status) == ("channels.list", 1, 200)


def test_http_errors_are_classified_and_still_metered(db: Session, env: Env) -> None:
    body = {"error": {"code": 403, "errors": [{"reason": "quotaExceeded"}]}}
    yt = _client(httpx.MockTransport(lambda _: httpx.Response(403, content=json.dumps(body))))
    with pytest.raises(YouTubeApiError) as exc:
        yt.my_channel(CallContext(db=db, gcp_project="default", access_token="tok"))
    assert exc.value.error_class is ErrorClass.QUOTA_EXCEEDED
    assert db.scalars(select(QuotaLedger)).one().error_reason == "quotaExceeded"
    # The rest of today's DEFAULT bucket is now held until the PT reset.
    with pytest.raises(quota.QuotaExhausted):
        quota.reserve(db, project="default", method="videos.list", purpose="t")


def test_http_network_failure_is_transient(db: Session, env: Env) -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("reset")

    yt = _client(httpx.MockTransport(boom))
    with pytest.raises(YouTubeApiError) as exc:
        yt.my_channel(CallContext(db=db, gcp_project="default", access_token="tok"))
    assert exc.value.error_class is ErrorClass.TRANSIENT and exc.value.retryable


def test_only_allowlisted_hosts(db: Session, env: Env) -> None:
    yt = _client(httpx.MockTransport(lambda _: httpx.Response(200)))
    with pytest.raises(YouTubeApiError):
        yt.request(
            CallContext(db=db, gcp_project="default", access_token="tok"),
            "channels.list",
            "GET",
            "https://evil.example.com/youtube/v3/channels",
        )
    assert db.scalar(select(func.count()).select_from(QuotaLedger)) == 0
