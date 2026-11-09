"""Channels API, onboarding, private test upload (resumable, fault-injected), retention, notifications."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from tests.integration.conftest import BASE_URL, OWNER_PASSWORD, Env, login
from tests.integration.test_oauth_flow import CLIENT_ID, YT_ID, FakeGoogle
from tubeforge.db.ids import uuid7
from tubeforge.db.models import (
    Channel,
    Notification,
    OnboardingStep,
    QuotaLedger,
    UploadJob,
    VideoProject,
    WorkflowTransition,
    YoutubeApiCache,
)
from tubeforge.main import create_app
from tubeforge.youtube import oauth, retention, uploads
from tubeforge.youtube.client import SafeYouTubeClient

pytestmark = pytest.mark.integration

SESSION = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=s-1"


class WorkerDiedError(Exception):
    """Simulates the worker process dying."""


@dataclass
class FakeYouTube(FakeGoogle):
    """FakeGoogle + Google's resumable upload protocol, with fault injection."""

    sessions: int = 0
    metadata: list[dict[str, object]] = field(default_factory=list)
    received: bytearray = field(default_factory=bytearray)
    total: int = 0
    puts: int = 0
    faults: dict[int, str] = field(default_factory=dict)  # PUT number -> "network" | "503" | "half-network"
    existing_videos: set[str] = field(default_factory=lambda: {"vid-1"})

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if req.url.path == "/upload/youtube/v3/videos" and req.method == "POST":
            self.sessions += 1
            self.metadata.append(json.loads(req.content))
            self.total = int(req.headers["X-Upload-Content-Length"])
            return httpx.Response(200, headers={"Location": SESSION})
        if req.url.path == "/upload/youtube/v3/videos" and req.method == "PUT":
            return self._put(req)
        if req.url.path == "/youtube/v3/videos":
            ids = req.url.params["id"].split(",")
            return httpx.Response(200, json={"items": [{"id": i} for i in ids if i in self.existing_videos]})
        return super().__call__(req)

    def _status(self) -> httpx.Response:
        if len(self.received) == self.total:
            return httpx.Response(
                201, json={"id": "vid-1", "status": {"uploadStatus": "uploaded", "privacyStatus": "private"}}
            )
        headers = {"Range": f"bytes=0-{len(self.received) - 1}"} if self.received else {}
        return httpx.Response(308, headers=headers)

    def _put(self, req: httpx.Request) -> httpx.Response:
        rng = req.headers["Content-Range"]
        if rng.startswith("bytes */"):
            return self._status()
        self.puts += 1
        start = int(rng.split()[1].split("-")[0])
        assert start == len(self.received), f"client resumed at {start}, server has {len(self.received)}"
        fault = self.faults.get(self.puts)
        if fault == "half-network":
            self.received += req.content[: len(req.content) // 2]
            raise httpx.ReadError("connection reset")
        if fault == "network":
            raise httpx.ConnectError("connection reset")
        if fault == "503":
            return httpx.Response(503, json={"error": {"code": 503, "errors": [{"reason": "backendError"}]}})
        self.received += req.content
        return self._status()


@dataclass
class World:
    env: Env
    client: TestClient
    headers: dict[str, str]
    yt: FakeYouTube
    app: object

    def post(self, path: str, json: object = None, **headers: str) -> httpx.Response:
        return self.client.post(
            path, json=json or {}, headers={**self.headers, "Idempotency-Key": str(uuid.uuid4()), **headers}
        )

    def db(self) -> Session:
        return Session(create_engine(self.env.db_url), expire_on_commit=False)

    @property
    def state(self):  # type: ignore[no-untyped-def]
        return self.app.state  # type: ignore[attr-defined]

    def reauth(self) -> None:
        r = self.client.post("/api/v1/auth/reauth", json={"password": OWNER_PASSWORD}, headers=self.headers)
        assert r.status_code == 204, r.text

    def new_channel(self, name: str = "Test channel") -> str:
        r = self.post("/api/v1/channels", {"name": name, "content_language": "en", "is_test_channel": True})
        assert r.status_code == 201, r.text
        return str(r.json()["id"])

    def connect(self, cid: str) -> None:
        if self.client.get(f"/api/v1/channels/{cid}").json()["state"] == "APPROVED":
            assert self.post(f"/api/v1/channels/{cid}/commands/start-onboarding").status_code == 200
        r = self.post("/api/v1/oauth/youtube/start", {"channel_id": cid})
        params = httpx.URL(r.json()["authorization_url"]).params
        code = f"code-{uuid.uuid4().hex[:6]}"
        self.yt.challenges[code] = params["code_challenge"]
        page = TestClient(self.client.app, base_url=BASE_URL).get(
            "/oauth/callback", params={"state": params["state"], "code": code}
        )
        assert page.status_code == 200, page.text
        r = self.post(f"/api/v1/channels/{cid}/oauth/confirm-identity", {"youtube_channel_id": YT_ID})
        assert r.json()["state"] == "CONNECTED", r.text

    def run_job(self, job_id: str, **kw: object) -> UploadJob:
        with self.db() as db:
            return uploads.run_upload_job(
                db,
                self.state.secret_box,
                self.state.google_oauth,
                self.state.youtube,
                uuid.UUID(job_id),
                sleep=kw.pop("sleep", lambda _s: None),  # type: ignore[arg-type]
                **kw,  # type: ignore[arg-type]
            )


@pytest.fixture
def world(env: Env) -> Iterator[World]:
    yt = FakeYouTube()
    app = create_app(env.app_settings)
    app.state.google_oauth = oauth.GoogleOAuth(transport=httpx.MockTransport(yt))
    app.state.youtube = SafeYouTubeClient(transport=httpx.MockTransport(yt))
    with TestClient(app, base_url=BASE_URL) as client:
        headers = login(client)
        w = World(env, client, headers, yt, app)
        r = w.post(
            "/api/v1/oauth/clients",
            {"label": "Desktop", "client_id": CLIENT_ID, "client_secret": "s3cret-value"},
        )
        assert r.status_code == 201
        yield w


# ------------------------------------------------------------------------------------- lifecycle
def test_create_onboard_connect(world: World) -> None:
    cid = world.new_channel()
    assert world.client.get(f"/api/v1/channels/{cid}").json()["state"] == "APPROVED"
    assert world.post(f"/api/v1/channels/{cid}/commands/pause").json()["code"] == "INVALID_TRANSITION"
    world.post(f"/api/v1/channels/{cid}/commands/start-onboarding")
    steps = {s["step_code"]: s for s in world.client.get(f"/api/v1/channels/{cid}/onboarding").json()}
    assert len(steps) == 10 and steps["OAUTH_CLIENT"]["status"] == "DONE"  # a client is registered
    ok = world.client.patch(
        f"/api/v1/channels/{cid}/onboarding/VERIFY_PHONE", json={"status": "DONE"}, headers=world.headers
    )
    assert ok.json()["status"] == "DONE"
    sys_step = world.client.patch(
        f"/api/v1/channels/{cid}/onboarding/CONNECT", json={"status": "DONE"}, headers=world.headers
    )
    assert sys_step.json()["code"] == "SYSTEM_STEP"

    world.connect(cid)
    ch = world.client.get(f"/api/v1/channels/{cid}").json()
    assert ch["private_only_mode"] is True and ch["oauth_status"] == "ACTIVE"
    steps = {
        s["step_code"]: s["status"] for s in world.client.get(f"/api/v1/channels/{cid}/onboarding").json()
    }
    assert steps["CONNECT"] == "DONE" and steps["TEST_UPLOAD"] == "TODO"
    with world.db() as db:
        path = [
            (t.from_state, t.to_state)
            for t in db.scalars(select(WorkflowTransition).order_by(WorkflowTransition.id))
        ]
    assert path == [("APPROVED", "ONBOARDING"), ("ONBOARDING", "CONNECTED")]
    listed = world.client.get("/api/v1/channels", params={"state": "CONNECTED"}).json()
    assert [c["id"] for c in listed["items"]] == [cid]


def test_patch_needs_if_match_and_detects_conflicts(world: World) -> None:
    cid = world.new_channel()
    r = world.client.patch(f"/api/v1/channels/{cid}", json={"name": "New"}, headers=world.headers)
    assert r.status_code == 428
    ok = world.client.patch(
        f"/api/v1/channels/{cid}", json={"name": "New"}, headers={**world.headers, "If-Match": '"1"'}
    )
    assert ok.json()["name"] == "New" and ok.json()["version"] == 2
    stale = world.client.patch(
        f"/api/v1/channels/{cid}", json={"name": "Old"}, headers={**world.headers, "If-Match": '"1"'}
    )
    assert stale.status_code == 412 and stale.json()["current_version"] == 2
    bad_tz = world.client.patch(
        f"/api/v1/channels/{cid}",
        json={"audience_timezone": "Mars/Base"},
        headers={**world.headers, "If-Match": '"2"'},
    )
    assert bad_tz.status_code == 400


# ------------------------------------------------------------------------------------ test upload
def test_private_test_upload_end_to_end(world: World) -> None:
    cid = world.new_channel()
    world.connect(cid)
    r = world.post(f"/api/v1/channels/{cid}/test-upload")
    assert r.status_code == 202, r.text
    job = r.json()
    assert (job["state"], job["privacy_status"], job["is_test"]) == ("PREFLIGHT", "private", True)
    with world.db() as db:
        queued = db.execute(
            text(
                "SELECT queue_name, args->>'upload_job_id' FROM procrastinate_jobs"
                " WHERE task_name LIKE '%yt.upload'"
            )
        ).all()
    assert queued == [("youtube", job["id"])]

    done = world.run_job(job["id"])
    assert (done.state, done.youtube_video_id) == ("COMPLETED", "vid-1")
    [meta] = world.yt.metadata
    assert meta["status"] == {
        "privacyStatus": "private",
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": False,
    }
    assert bytes(world.yt.received) == uploads.TEST_CLIP.read_bytes()

    # Re-running the same job never uploads again.
    world.run_job(job["id"])
    assert world.yt.sessions == 1 and world.yt.puts == 1

    ch = world.client.get(f"/api/v1/channels/{cid}").json()
    assert ch["successful_private_test_uploads"] == 1 and ch["state"] == "CONNECTED"  # no privacy URL yet
    activated = world.client.patch(
        f"/api/v1/channels/{cid}",
        json={"privacy_policy_url": "https://owner.github.io/tubeforge/privacy.html"},
        headers={**world.headers, "If-Match": f'"{ch["version"]}"'},
    )
    assert activated.json()["state"] == "ACTIVE"
    assert world.client.get(f"/api/v1/uploads/{job['id']}").json()["youtube_video_id"] == "vid-1"
    with world.db() as db:
        assert db.scalars(select(QuotaLedger.method)).all().count("videos.insert") == 1
        assert db.get_one(VideoProject, uuid.UUID(done.project_id.hex)).state == "PRIVATE_DONE"
    summary = world.client.get("/api/v1/notifications/summary").json()
    assert summary["unread"] >= 1
    quota = world.client.get("/api/v1/quota").json()
    buckets = {b["bucket"]: b for b in quota[0]["buckets"]}
    assert buckets["VIDEO_UPLOADS"]["used"] == 1 and len(quota[0]["forecast"]) == 7


def _big_job(world: World, tmp_path: Path, size: int = 700 * 1024) -> tuple[str, Path]:
    cid = world.new_channel()
    world.connect(cid)
    job_id = world.post(f"/api/v1/channels/{cid}/test-upload").json()["id"]
    path = tmp_path / "big.mp4"
    path.write_bytes(os.urandom(size))
    world.env.sql(
        "UPDATE upload_jobs SET file_sha256 = :s, bytes_total = :n WHERE id = :i",
        s=hashlib.sha256(path.read_bytes()).hexdigest(),
        n=size,
        i=job_id,
    )
    return job_id, path


def test_resume_after_network_and_server_errors(world: World, tmp_path: Path) -> None:
    job_id, path = _big_job(world, tmp_path)
    world.yt.faults = {2: "half-network", 3: "503"}
    waits: list[float] = []
    done = world.run_job(job_id, file_path=path, chunk_size=256 * 1024, sleep=waits.append)
    assert done.state == "COMPLETED"
    assert bytes(world.yt.received) == path.read_bytes()  # every byte exactly once, in order
    assert world.yt.sessions == 1
    assert waits == [10.0, 20.0]  # backoff 2^n × 5 s


def test_worker_crash_resumes_from_saved_offset(world: World, tmp_path: Path) -> None:
    job_id, path = _big_job(world, tmp_path)
    world.yt.faults = {2: "network"}

    def die(_: float) -> None:
        raise WorkerDiedError

    with pytest.raises(WorkerDiedError):
        world.run_job(job_id, file_path=path, chunk_size=256 * 1024, sleep=die)
    with world.db() as db:
        job = db.get_one(UploadJob, uuid.UUID(job_id))
        assert job.state == "RESUMING" and job.bytes_confirmed == 256 * 1024
        assert job.session_uri_enc is not None and b"upload_id" not in job.session_uri_enc  # encrypted
    world.yt.faults = {}
    done = world.run_job(job_id, file_path=path, chunk_size=256 * 1024)
    assert done.state == "COMPLETED" and world.yt.sessions == 1
    assert bytes(world.yt.received) == path.read_bytes()


def test_gives_up_after_max_resumes(world: World, tmp_path: Path) -> None:
    job_id, path = _big_job(world, tmp_path)
    world.yt.faults = dict.fromkeys(range(2, 20), "503")
    failed = world.run_job(job_id, file_path=path, chunk_size=256 * 1024, max_resumes=3)
    assert (failed.state, failed.error_class) == ("FAILED", "TRANSIENT")
    with world.db() as db:
        assert db.scalars(select(Notification).where(Notification.event_type == "upload.failed")).first()


def test_changed_file_is_refused(world: World, tmp_path: Path) -> None:
    job_id, path = _big_job(world, tmp_path)
    path.write_bytes(b"something else")
    assert world.run_job(job_id, file_path=path).error_detail == "the file changed after approval"
    assert world.yt.sessions == 0


def test_test_upload_safety_checks(world: World) -> None:
    cid = world.new_channel()
    r = world.post(f"/api/v1/channels/{cid}/test-upload")
    assert r.status_code == 409 and r.json()["code"] == "REFUSED_CHANNEL_STATE"
    world.connect(cid)
    world.env.sql("UPDATE system_settings SET emergency_stop = true")
    r = world.post(f"/api/v1/channels/{cid}/test-upload")
    assert r.json()["code"] == "REFUSED_EMERGENCY_STOP"
    with world.db() as db:
        assert db.scalar(select(func.count()).select_from(UploadJob)) == 0


# ------------------------------------------------------------------------------- modes & rules
def test_private_only_and_mode_guards_need_step_up(world: World) -> None:
    cid = world.new_channel()
    world.connect(cid)
    r = world.post(f"/api/v1/channels/{cid}/private-only", {"enabled": False})
    assert r.status_code == 403 and r.json()["code"] == "REAUTH_REQUIRED"
    world.reauth()
    r = world.post(f"/api/v1/channels/{cid}/private-only", {"enabled": False})
    assert r.json()["code"] == "GUARDS_FAILED" and r.json()["guards"][0]["code"] == "TEST_UPLOADS"
    world.env.sql("UPDATE channels SET successful_private_test_uploads = 3")
    assert (
        world.post(f"/api/v1/channels/{cid}/private-only", {"enabled": False}).json()["private_only_mode"]
        is False
    )

    r = world.post(f"/api/v1/channels/{cid}/mode", {"mode": "FULLY_AUTOMATIC"})
    assert {g["code"] for g in r.json()["guards"]} == {"TEST_RUNS", "PUBLIC_RELEASE_TEST", "AUTO_RULES"}
    assert world.post(f"/api/v1/channels/{cid}/mode", {"mode": "SEMI_AUTOMATIC"}).json()[
        "operating_mode"
    ] == ("SEMI_AUTOMATIC")


def test_publishing_rules_and_auto_rule_acceptance(world: World) -> None:
    cid = world.new_channel()
    got = world.client.get(f"/api/v1/channels/{cid}/publishing-rules")
    rules = got.json()
    assert got.headers["ETag"] == '"1"' and rules["max_long_per_day"] == 1
    body = {
        k: rules[k]
        for k in rules
        if k not in {"channel_id", "auto_publish_rules_sha256", "auto_publish_accepted_at", "version"}
    }
    body["auto_publish_rules"] = {"min_scores": {"originality": 80}}
    assert (
        world.client.put(
            f"/api/v1/channels/{cid}/publishing-rules", json=body, headers=world.headers
        ).status_code
        == 428
    )
    put = world.client.put(
        f"/api/v1/channels/{cid}/publishing-rules", json=body, headers={**world.headers, "If-Match": '"1"'}
    )
    assert put.status_code == 200 and put.json()["version"] == 2
    sha = put.json()["auto_publish_rules_sha256"]
    world.reauth()
    wrong = world.post(
        f"/api/v1/channels/{cid}/publishing-rules/accept-auto-rules", {"rules_sha256": "0" * 64}
    )
    assert wrong.json()["code"] == "RULES_CHANGED"
    ok = world.post(f"/api/v1/channels/{cid}/publishing-rules/accept-auto-rules", {"rules_sha256": sha})
    assert ok.json()["auto_publish_accepted_at"] is not None
    body["auto_publish_rules"] = {"min_scores": {"originality": 60}}  # changing the rules resets consent
    again = world.client.put(
        f"/api/v1/channels/{cid}/publishing-rules", json=body, headers={**world.headers, "If-Match": '"2"'}
    )
    assert again.json()["auto_publish_accepted_at"] is None


# --------------------------------------------------------------------------- disconnect / delete
def test_pause_resume_disconnect_delete(world: World) -> None:
    cid = world.new_channel()
    world.connect(cid)
    assert world.post(f"/api/v1/channels/{cid}/commands/pause").json()["state"] == "PAUSED"
    assert world.post(f"/api/v1/channels/{cid}/commands/resume").json()["state"] == "CONNECTED"
    r = world.client.delete(f"/api/v1/channels/{cid}", headers=world.headers)
    assert r.status_code == 403  # step-up first
    assert world.post(f"/api/v1/channels/{cid}/commands/disconnect").json()["code"] == "REAUTH_REQUIRED"
    world.reauth()
    assert (
        world.client.delete(f"/api/v1/channels/{cid}", headers=world.headers).json()["code"]
        == "CHANNEL_IN_USE"
    )
    assert world.post(f"/api/v1/channels/{cid}/commands/disconnect").json()["state"] == "DISCONNECTING"
    assert world.yt.revoked == ["rt-1"]

    with world.db() as db:
        result = retention.run_deletion_tasks(db)
        db.commit()
    assert result.completed == 1
    ch = world.client.get(f"/api/v1/channels/{cid}").json()
    assert ch["state"] == "DISCONNECTED" and ch["oauth_status"] == "NOT_CONNECTED"
    assert world.post(f"/api/v1/channels/{cid}/commands/reconnect").json()["state"] == "ONBOARDING"
    steps = {
        s["step_code"]: s["status"] for s in world.client.get(f"/api/v1/channels/{cid}/onboarding").json()
    }
    assert steps["CONNECT"] == "TODO"
    assert world.client.delete(f"/api/v1/channels/{cid}", headers=world.headers).status_code == 204
    assert world.client.get(f"/api/v1/channels/{cid}").status_code == 404


def test_owner_can_request_api_data_deletion(world: World) -> None:
    cid = world.new_channel()
    world.reauth()
    r = world.post(f"/api/v1/channels/{cid}/delete-api-data")
    assert r.status_code == 202 and r.json()["reason"] == "OWNER_REQUEST"


# ------------------------------------------------------------------------------------- retention
def test_retention_purges_and_reauthorize_check(world: World) -> None:
    cid = world.new_channel()
    world.connect(cid)
    now = datetime.now(UTC)
    with world.db() as db:
        db.add(
            YoutubeApiCache(
                id=uuid7(),
                requested_by=world.env.owner.id,
                lookup_kind="VIDEO",
                query_key="x",
                response={},
                fetched_at=now - timedelta(days=31),
                expires_at=now - timedelta(days=1),
            )
        )
        project = VideoProject(
            id=uuid7(),
            channel_id=uuid.UUID(cid),
            format="LONG",
            state="PUBLISHED",
            working_title="Gone",
            target_duration_s=60,
            render_profile={},
            youtube_video_id="vid-gone",
        )
        db.add(project)
        db.commit()
        assert retention.purge_api_cache(db) == 1
        world.env.sql("UPDATE oauth_connections SET last_authorization_check_at = now() - interval '26 days'")
        db.expire_all()
        result = retention.reauthorize_check(
            db, world.state.secret_box, world.state.google_oauth, world.state.youtube
        )
        db.commit()
        assert (result.checked, result.removed_videos) == (1, ["vid-gone"])
        assert db.get_one(VideoProject, project.id).youtube_video_id is None
        # Checked recently → skipped next time.
        assert (
            retention.reauthorize_check(
                db, world.state.secret_box, world.state.google_oauth, world.state.youtube
            ).checked
            == 0
        )


# ---------------------------------------------------------------------------------- notifications
def test_notifications_bell(world: World, add_user) -> None:  # type: ignore[no-untyped-def]
    with world.db() as db:
        from tubeforge.notifications import notify_owners

        notify_owners(db, event_type="t", severity="CRITICAL", title="A", body="b", dedup_key="k1")
        notify_owners(db, event_type="t", severity="INFO", title="B", body="b", dedup_key="k2")
        db.commit()
    assert world.client.get("/api/v1/notifications/summary").json() == {"unread": 2, "critical_unread": 1}
    items = world.client.get("/api/v1/notifications", params={"severity": "CRITICAL"}).json()["items"]
    assert [i["title"] for i in items] == ["A"]
    assert (
        world.client.post(f"/api/v1/notifications/{items[0]['id']}/read", headers=world.headers).status_code
        == 204
    )
    assert world.client.get("/api/v1/notifications/summary").json()["unread"] == 1
    add_user("viewer@example.com", "VIEWER")
    with TestClient(world.client.app, base_url=BASE_URL) as other:
        h = login(other, "viewer@example.com")
        assert other.post(f"/api/v1/notifications/{items[0]['id']}/read", headers=h).status_code == 404
        assert other.get("/api/v1/notifications/summary").json()["unread"] == 0
    world.client.post("/api/v1/notifications/read-all", headers=world.headers)
    assert world.client.get("/api/v1/notifications/summary").json()["unread"] == 0
    with world.db() as db:
        assert db.scalar(select(func.count()).select_from(OnboardingStep)) == 0
        assert db.scalar(select(func.count()).select_from(Channel)) == 0
