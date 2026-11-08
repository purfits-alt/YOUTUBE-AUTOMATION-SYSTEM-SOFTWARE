"""Google OAuth for YouTube against a fake Google (OAUTH_SECURITY §4): PKCE, state, scopes, tokens,
identity confirmation, refresh failure → NEEDS_REAUTH, Testing-mode expiry warning, disconnect."""

from __future__ import annotations

import base64
import hashlib
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tests.integration.conftest import BASE_URL, Env, login
from tubeforge.db.ids import uuid7
from tubeforge.db.models import (
    Channel,
    DataDeletionTask,
    Notification,
    OAuthClient,
    OAuthConnection,
    OAuthPendingFlow,
    QuotaLedger,
    SecurityEvent,
)
from tubeforge.main import create_app
from tubeforge.youtube import oauth
from tubeforge.youtube.client import SafeYouTubeClient

pytestmark = pytest.mark.integration

CLIENT_ID = "123456789-abcdef.apps.googleusercontent.com"
YT_ID = "UC" + "a" * 22
OTHER_YT_ID = "UC" + "b" * 22
FULL = f"{oauth.UPLOAD} {oauth.READONLY}"


@dataclass
class FakeGoogle:
    """Token, revoke and channels.list endpoints. Verifies PKCE like Google does."""

    challenges: dict[str, str] = field(default_factory=dict)  # code -> code_challenge
    granted: str = FULL
    give_refresh: bool = True
    refresh_fails: bool = False
    youtube_id: str = YT_ID
    refreshes: int = 0
    revoked: list[str] = field(default_factory=list)
    counter: int = 0

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if req.url.host == "oauth2.googleapis.com" and req.url.path == "/token":
            form = parse_qs(req.content.decode())
            assert form["client_id"] == [CLIENT_ID]
            assert form["client_secret"] == ["s3cret-value"]
            if form["grant_type"] == ["authorization_code"]:
                code = form["code"][0]
                verifier = form["code_verifier"][0]
                digest = hashlib.sha256(verifier.encode()).digest()
                if base64.urlsafe_b64encode(digest).rstrip(b"=").decode() != self.challenges.get(code):
                    return httpx.Response(400, json={"error": "invalid_grant", "error_description": "PKCE"})
                assert form["redirect_uri"] == ["http://127.0.0.1:8765/oauth/callback"]
                self.counter += 1
                body = {"access_token": f"at-{self.counter}", "expires_in": 3599, "scope": self.granted}
                if self.give_refresh:
                    body["refresh_token"] = f"rt-{self.counter}"
                return httpx.Response(200, json=body)
            self.refreshes += 1
            if self.refresh_fails:
                return httpx.Response(400, json={"error": "invalid_grant", "error_description": "expired"})
            return httpx.Response(200, json={"access_token": f"at-r{self.refreshes}", "expires_in": 3599})
        if req.url.path == "/revoke":
            self.revoked.append(parse_qs(req.content.decode())["token"][0])
            return httpx.Response(200)
        if req.url.path == "/youtube/v3/channels":
            assert req.headers["Authorization"].startswith("Bearer at-")
            item = {"id": self.youtube_id, "snippet": {"title": "My Test Channel", "customUrl": "@mytest"}}
            return httpx.Response(200, json={"items": [item]})
        return httpx.Response(404)


@dataclass
class Ctx:
    env: Env
    client: TestClient
    headers: dict[str, str]
    google: FakeGoogle
    channel_id: uuid.UUID
    app_state: object

    def post(self, path: str, json: object) -> httpx.Response:
        return self.client.post(
            path, json=json, headers={**self.headers, "Idempotency-Key": str(uuid.uuid4())}
        )

    def db(self) -> Session:
        return Session(create_engine(self.env.db_url), expire_on_commit=False)

    def start(self, features: list[str] | None = None) -> dict[str, list[str]]:
        r = self.post(
            "/api/v1/oauth/youtube/start", {"channel_id": str(self.channel_id), "features": features or []}
        )
        assert r.status_code == 200, r.text
        return parse_qs(urlparse(r.json()["authorization_url"]).query)

    def consent(self, params: dict[str, list[str]], code: str = "code-1") -> httpx.Response:
        """What Google does after the owner clicks Allow: redirect to the loopback callback."""
        self.google.challenges[code] = params["code_challenge"][0]
        fresh = TestClient(
            self.client.app, base_url=BASE_URL
        )  # Google's redirect: no TubeForge cookies needed
        return fresh.get("/oauth/callback", params={"state": params["state"][0], "code": code})


@pytest.fixture
def ctx(env: Env) -> Iterator[Ctx]:
    google = FakeGoogle()
    app = create_app(env.app_settings)
    app.state.google_oauth = oauth.GoogleOAuth(transport=httpx.MockTransport(google))
    app.state.youtube = SafeYouTubeClient(transport=httpx.MockTransport(google))
    channel_id = uuid7()
    env.sql(
        "INSERT INTO channels (id, name, state, content_language)"
        " VALUES (:i, 'Test channel', 'ONBOARDING', 'en')",
        i=channel_id,
    )
    with TestClient(app, base_url=BASE_URL) as client:
        headers = login(client)
        c = Ctx(env, client, headers, google, channel_id, app.state)
        r = c.post(
            "/api/v1/oauth/clients",
            {
                "label": "Desktop",
                "client_id": CLIENT_ID,
                "client_secret": "s3cret-value",
                "gcp_project_id": "tubeforge-yt",
            },
        )
        assert r.status_code == 201, r.text
        yield c


def connect(c: Ctx) -> None:
    page = c.consent(c.start())
    assert page.status_code == 200, page.text
    r = c.post(f"/api/v1/channels/{c.channel_id}/oauth/confirm-identity", {"youtube_channel_id": YT_ID})
    assert r.status_code == 200, r.text


# ------------------------------------------------------------------------------------------ tests
def test_client_secret_is_write_only_and_encrypted(ctx: Ctx) -> None:
    [row] = ctx.client.get("/api/v1/oauth/clients").json()
    assert row["has_secret"] is True and "client_secret" not in row
    with ctx.db() as db:
        stored = db.scalars(select(OAuthClient)).one()
        assert stored.client_secret_enc is not None and b"s3cret-value" not in stored.client_secret_enc
    bad = ctx.post("/api/v1/oauth/clients", {"label": "x", "client_id": "not-a-client-id"})
    assert bad.status_code == 400


def test_full_connect_flow(ctx: Ctx) -> None:
    params = ctx.start()
    assert params["code_challenge_method"] == ["S256"]
    assert params["access_type"] == ["offline"] and params["prompt"] == ["consent"]
    assert params["redirect_uri"] == ["http://127.0.0.1:8765/oauth/callback"]
    assert set(params["scope"][0].split()) == {oauth.UPLOAD, oauth.READONLY}  # least privilege
    assert len(params["state"][0]) == 43 and "code_verifier" not in params

    page = ctx.consent(params)
    assert page.status_code == 200 and "confirm it is the right channel" in page.text
    assert page.headers["Referrer-Policy"] == "no-referrer"

    with ctx.db() as db:
        conn = db.scalars(select(OAuthConnection)).one()
        assert conn.status == "ACTIVE" and b"rt-1" not in conn.refresh_token_enc
        assert conn.access_token_enc is not None and b"at-1" not in conn.access_token_enc
        assert conn.refresh_expected_expiry is not None  # Testing mode: 7 days
        assert db.scalar(select(OAuthPendingFlow)) is None  # state consumed

    who = ctx.client.get(f"/api/v1/channels/{ctx.channel_id}/oauth/identity")
    assert who.json() == {"youtube_channel_id": YT_ID, "title": "My Test Channel", "handle": "@mytest"}
    wrong = ctx.post(
        f"/api/v1/channels/{ctx.channel_id}/oauth/confirm-identity", {"youtube_channel_id": OTHER_YT_ID}
    )
    assert wrong.status_code == 409 and wrong.json()["code"] == "IDENTITY_MISMATCH"
    ok = ctx.post(f"/api/v1/channels/{ctx.channel_id}/oauth/confirm-identity", {"youtube_channel_id": YT_ID})
    assert ok.json()["state"] == "CONNECTED" and ok.json()["youtube_handle"] == "@mytest"

    health = ctx.client.get(f"/api/v1/channels/{ctx.channel_id}/oauth/health").json()
    assert health["status"] == "ACTIVE" and health["scopes"] == ["youtube.readonly", "youtube.upload"]
    assert health["expiring_soon"] is False and health["publishing_status"] == "TESTING"
    assert ctx.google.refreshes == 0  # cached access token reused
    with ctx.db() as db:
        ledger = db.scalars(select(QuotaLedger)).all()
        assert {(r.method, r.gcp_project) for r in ledger} == {("channels.list", "tubeforge-yt")}


def test_state_is_single_use_and_unknown_state_is_logged(ctx: Ctx) -> None:
    params = ctx.start()
    assert ctx.consent(params).status_code == 200
    again = ctx.consent(params, code="code-2")
    assert again.status_code == 400 and "not valid" in again.text
    with ctx.db() as db:
        assert db.scalars(select(SecurityEvent).where(SecurityEvent.kind == "OAUTH_STATE_UNKNOWN")).first()


def test_expired_state(ctx: Ctx) -> None:
    params = ctx.start()
    ctx.env.sql("UPDATE oauth_pending_flows SET expires_at = now() - interval '1 second'")
    page = ctx.consent(params)
    assert page.status_code == 400 and "10 minutes" in page.text


def test_wrong_pkce_verifier_is_rejected_by_google(ctx: Ctx) -> None:
    params = ctx.start()
    params["code_challenge"] = ["forged"]
    page = ctx.consent(params)
    assert page.status_code == 502
    with ctx.db() as db:
        assert db.scalar(select(OAuthConnection)) is None


def test_consent_denied(ctx: Ctx) -> None:
    params = ctx.start()
    fresh = TestClient(ctx.client.app, base_url=BASE_URL)
    page = fresh.get("/oauth/callback", params={"state": params["state"][0], "error": "access_denied"})
    assert page.status_code == 400 and "cancelled" in page.text


def test_unticked_scope_is_refused_and_token_returned(ctx: Ctx) -> None:
    ctx.google.granted = oauth.UPLOAD  # owner un-ticked "see your YouTube account"
    page = ctx.consent(ctx.start())
    assert page.status_code == 400 and "youtube.readonly" in page.text
    assert ctx.google.revoked == ["at-1"]
    with ctx.db() as db:
        assert db.scalar(select(OAuthConnection)) is None


def test_incremental_consent_adds_scope_and_keeps_refresh_token(ctx: Ctx) -> None:
    connect(ctx)
    params = parse_qs(
        urlparse(
            ctx.post(
                f"/api/v1/channels/{ctx.channel_id}/oauth/incremental", {"features": ["captions"]}
            ).json()["authorization_url"]
        ).query
    )
    assert oauth.FORCE_SSL in params["scope"][0].split() and "prompt" not in params
    ctx.google.granted = f"{FULL} {oauth.FORCE_SSL}"
    ctx.google.give_refresh = False
    assert ctx.consent(params, code="code-2").status_code == 200
    with ctx.db() as db:
        conn = db.scalars(select(OAuthConnection)).one()
        assert oauth.FORCE_SSL in conn.scopes
        box = ctx.app_state.secret_box  # type: ignore[attr-defined]
        assert oauth._open_token(box, conn, "refresh_token_enc", conn.refresh_token_enc) == "rt-1"
    bad = ctx.post(f"/api/v1/channels/{ctx.channel_id}/oauth/incremental", {"features": ["monetary"]})
    assert bad.status_code == 400


def test_refresh_failure_marks_needs_reauth_then_reconnect(ctx: Ctx) -> None:
    connect(ctx)
    ctx.google.refresh_fails = True
    state = ctx.app_state
    with ctx.db() as db:
        result = oauth.token_health(db, state.secret_box, state.google_oauth)  # type: ignore[attr-defined]
        db.commit()
    assert (result.checked, result.needs_reauth) == (1, 1)
    with ctx.db() as db:
        channel = db.get_one(Channel, ctx.channel_id)
        assert (channel.state, channel.resume_to_state) == ("NEEDS_REAUTH", "CONNECTED")
        [note] = db.scalars(select(Notification)).all()
        assert (note.event_type, note.severity) == ("oauth.revoked", "CRITICAL")
    assert (
        ctx.client.get(f"/api/v1/channels/{ctx.channel_id}/oauth/identity").json()["code"]
        == "OAUTH_NEEDS_REAUTH"
    )

    # Re-authorising with a different YouTube channel is refused …
    ctx.google.refresh_fails = False
    ctx.google.youtube_id = OTHER_YT_ID
    page = ctx.consent(ctx.start(), code="code-2")
    assert page.status_code == 400 and "different YouTube channel" in page.text
    # … the same channel brings it back to where it was.
    ctx.google.youtube_id = YT_ID
    params = ctx.start()
    assert params["prompt"] == ["consent"]
    assert ctx.consent(params, code="code-3").status_code == 200
    with ctx.db() as db:
        assert db.get_one(Channel, ctx.channel_id).state == "CONNECTED"


def test_testing_mode_expiry_warning_is_deduplicated(ctx: Ctx) -> None:
    connect(ctx)
    ctx.env.sql("UPDATE oauth_connections SET refresh_expected_expiry = now() + interval '10 hours'")
    state = ctx.app_state
    for _ in range(2):
        with ctx.db() as db:
            result = oauth.token_health(db, state.secret_box, state.google_oauth)  # type: ignore[attr-defined]
            db.commit()
        assert result.expiring == 1 and result.refreshed == 1
    with ctx.db() as db:
        notes = db.scalars(select(Notification).where(Notification.event_type == "oauth.expiring")).all()
        assert len(notes) == 1
    assert ctx.client.get(f"/api/v1/channels/{ctx.channel_id}/oauth/health").json()["expiring_soon"] is True


def test_disconnect_revokes_deletes_tokens_and_schedules_deletion(ctx: Ctx) -> None:
    connect(ctx)
    state = ctx.app_state
    with ctx.db() as db:
        channel = db.get_one(Channel, ctx.channel_id)
        from tubeforge.audit import SYSTEM

        task = oauth.disconnect(db, state.secret_box, state.google_oauth, channel, actor=SYSTEM)  # type: ignore[attr-defined]
        db.commit()
        assert task.due_at - datetime.now(UTC) > timedelta(days=6, hours=23)
    assert ctx.google.revoked == ["rt-1"]
    with ctx.db() as db:
        assert db.scalar(select(OAuthConnection)) is None
        assert db.get_one(Channel, ctx.channel_id).state == "DISCONNECTING"
        assert db.scalars(select(DataDeletionTask)).one().reason == "DISCONNECT"
    assert (
        ctx.client.get(f"/api/v1/channels/{ctx.channel_id}/oauth/health").json()["status"] == "NOT_CONNECTED"
    )


def test_client_in_use_cannot_be_deleted_and_viewer_cannot_connect(ctx: Ctx, add_user) -> None:  # type: ignore[no-untyped-def]
    connect(ctx)
    [row] = ctx.client.get("/api/v1/oauth/clients").json()
    r = ctx.client.delete(f"/api/v1/oauth/clients/{row['id']}", headers=ctx.headers)
    assert r.status_code == 409 and r.json()["code"] == "CLIENT_IN_USE"
    add_user("viewer@example.com", "VIEWER")
    with TestClient(ctx.client.app, base_url=BASE_URL) as viewer:
        h = login(viewer, "viewer@example.com")
        r = viewer.post(
            "/api/v1/oauth/youtube/start",
            json={"channel_id": str(ctx.channel_id)},
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 403
        assert viewer.get(f"/api/v1/channels/{ctx.channel_id}/oauth/health").status_code == 200


def test_start_needs_a_connectable_channel(ctx: Ctx) -> None:
    ctx.env.sql("UPDATE channels SET state = 'APPROVED'")
    r = ctx.post("/api/v1/oauth/youtube/start", {"channel_id": str(ctx.channel_id)})
    assert r.status_code == 409 and r.json()["code"] == "CHANNEL_STATE"
