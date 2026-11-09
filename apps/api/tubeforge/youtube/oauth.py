"""Google OAuth for YouTube: PKCE loopback flow, tokens, identity, health, disconnect (OAUTH_SECURITY §4).

- ``state`` is 256-bit random, single use, 10-minute TTL (``oauth_pending_flows``); the PKCE verifier
  is stored encrypted. Code challenge method S256.
- Refresh and access tokens and the client secret are AES-GCM sealed with AAD ``table:column:row_id``.
  Tokens never leave this module except as an ``Authorization`` header to Google.
- Talks only to ``accounts.google.com`` (consent page, built as a URL) and ``oauth2.googleapis.com``.
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from tubeforge import channel_lifecycle as lifecycle
from tubeforge.audit import SYSTEM, Actor, record, security_event
from tubeforge.db.ids import uuid7
from tubeforge.db.models import (
    Channel,
    DataDeletionTask,
    OAuthClient,
    OAuthConnection,
    OAuthPendingFlow,
    OnboardingStep,
)
from tubeforge.notifications import notify_owners
from tubeforge.secrets import SecretBox, aad
from tubeforge.youtube import quota
from tubeforge.youtube.client import CallContext, SafeYouTubeClient
from tubeforge.youtube.errors import ErrorClass, YouTubeApiError, from_response

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - a URL, not a secret
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
OAUTH_HOSTS = frozenset({"oauth2.googleapis.com"})

_S = "https://www.googleapis.com/auth/"
UPLOAD = _S + "youtube.upload"
READONLY = _S + "youtube.readonly"
FORCE_SSL = _S + "youtube.force-ssl"
ANALYTICS = _S + "yt-analytics.readonly"
BASE_SCOPES = (UPLOAD, READONLY)
# Least privilege (§4.3): extra scopes only when the owner turns the feature on.
FEATURE_SCOPES: dict[str, str] = {
    "upload": UPLOAD,
    "readonly": READONLY,
    "captions": FORCE_SSL,
    "playlists": FORCE_SSL,
    "metadata": FORCE_SSL,
    "comments": FORCE_SSL,
    "analytics": ANALYTICS,
}
CLIENT_ID_RE = re.compile(r"^[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com$")
STATE_TTL = timedelta(minutes=10)
TESTING_REFRESH_LIFETIME = timedelta(days=7)  # Y12
EXPIRY_WARNING = timedelta(hours=24)
ACCESS_TOKEN_MARGIN = timedelta(seconds=60)
CONNECTABLE_STATES = {"ONBOARDING", "CONNECTED", "ACTIVE", "PAUSED", "NEEDS_REAUTH"}


class OAuthFlowError(Exception):
    """A flow problem the owner can fix. ``code`` is stable (used by the API and the callback page)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# ------------------------------------------------------------------------------------- scopes/PKCE
def scopes_for(features: list[str] | tuple[str, ...]) -> list[str]:
    unknown = sorted(set(features) - FEATURE_SCOPES.keys())
    if unknown:
        raise OAuthFlowError("UNKNOWN_FEATURE", f"Unknown feature(s): {', '.join(unknown)}")
    wanted = set(BASE_SCOPES) | {FEATURE_SCOPES[f] for f in features}
    return sorted(wanted)


def new_state() -> str:
    return secrets.token_urlsafe(32)  # 256 bits → 43 characters


def new_verifier() -> str:
    return secrets.token_urlsafe(64)  # 86 characters (RFC 7636: 43–128)


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def redirect_uri(port: int) -> str:
    return f"http://127.0.0.1:{port}/oauth/callback"


# --------------------------------------------------------------------------------------- Google
@dataclass(frozen=True)
class TokenResponse:
    access_token: str
    expires_in: int
    refresh_token: str | None
    scopes: list[str]


class GoogleOAuth:
    """Google's token and revoke endpoints over httpx (ADR-0026). Transport injectable for tests."""

    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = 30.0) -> None:
        self._http = httpx.Client(transport=transport, timeout=timeout, follow_redirects=False)

    def close(self) -> None:
        self._http.close()

    def _post(self, url: str, data: dict[str, str]) -> httpx.Response:
        if httpx.URL(url).host not in OAUTH_HOSTS:
            raise YouTubeApiError(ErrorClass.INVALID_REQUEST, None, None, "host not allowed")
        try:
            resp = self._http.post(url, data=data)
        except httpx.TransportError as exc:
            raise YouTubeApiError(ErrorClass.TRANSIENT, None, None, type(exc).__name__) from exc
        if resp.status_code >= 400:
            raise from_response(resp.status_code, resp.content)
        return resp

    @staticmethod
    def _tokens(resp: httpx.Response) -> TokenResponse:
        body: dict[str, Any] = resp.json()
        return TokenResponse(
            access_token=str(body["access_token"]),
            expires_in=int(body.get("expires_in", 3600)),
            refresh_token=body.get("refresh_token"),
            scopes=str(body.get("scope", "")).split(),
        )

    def exchange(
        self, *, client_id: str, client_secret: str | None, code: str, verifier: str, redirect: str
    ) -> TokenResponse:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": client_id,
            "redirect_uri": redirect,
        }
        if client_secret:
            data["client_secret"] = client_secret
        return self._tokens(self._post(TOKEN_URL, data))

    def refresh(self, *, client_id: str, client_secret: str | None, refresh_token: str) -> TokenResponse:
        data = {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id}
        if client_secret:
            data["client_secret"] = client_secret
        return self._tokens(self._post(TOKEN_URL, data))

    def revoke(self, token: str) -> None:
        self._post(REVOKE_URL, {"token": token})


# -------------------------------------------------------------------------------------- clients
def register_client(
    db: Session,
    box: SecretBox,
    *,
    label: str,
    client_id: str,
    client_secret: str | None,
    gcp_project_id: str | None,
    publishing_status: str = "TESTING",
) -> OAuthClient:
    if not CLIENT_ID_RE.match(client_id):
        raise OAuthFlowError("INVALID_CLIENT_ID", "That does not look like a Desktop-app OAuth client ID.")
    row = OAuthClient(
        id=uuid7(),
        label=label,
        client_id=client_id,
        gcp_project_id=gcp_project_id,
        publishing_status=publishing_status,
    )
    if client_secret:
        sealed = box.seal(
            client_secret.encode(),
            purpose="oauth-client",
            associated=aad("oauth_clients", "client_secret_enc", row.id),
        )
        row.client_secret_enc, row.key_id = sealed.ciphertext, sealed.key_id
    db.add(row)
    # Onboarding step "OAuth client" is done for every channel once a client exists.
    for step in db.scalars(
        select(OnboardingStep).where(
            OnboardingStep.step_code == "OAUTH_CLIENT", OnboardingStep.status == "TODO"
        )
    ):
        step.status, step.completed_at = "DONE", datetime.now(UTC)
    db.flush()
    return row


def _client_secret(box: SecretBox, client: OAuthClient) -> str | None:
    if client.client_secret_enc is None or client.key_id is None:
        return None
    return box.open(
        client.client_secret_enc,
        key_id=client.key_id,
        purpose="oauth-client",
        associated=aad("oauth_clients", "client_secret_enc", client.id),
    ).decode()


def current_connection(db: Session, channel_id: uuid.UUID) -> OAuthConnection | None:
    return db.scalar(
        select(OAuthConnection)
        .where(OAuthConnection.channel_id == channel_id, OAuthConnection.revoked_at.is_(None))
        .order_by(OAuthConnection.created_at.desc())
        .limit(1)
    )


def client_for(db: Session, channel_id: uuid.UUID) -> OAuthClient:
    """The channel's current client, else the newest registered one (the same rule at start and callback)."""
    conn = current_connection(db, channel_id)
    if conn is not None:
        client = db.get(OAuthClient, conn.oauth_client_id)
        if client is not None:
            return client
    client = db.scalar(select(OAuthClient).order_by(OAuthClient.created_at.desc(), OAuthClient.id.desc()))
    if client is None:
        raise OAuthFlowError("NO_OAUTH_CLIENT", "Add your Google OAuth client in onboarding first.")
    return client


def gcp_project(client: OAuthClient) -> str:
    return client.gcp_project_id or quota.DEFAULT_PROJECT


# ----------------------------------------------------------------------------------------- flow
def start_flow(
    db: Session,
    box: SecretBox,
    *,
    channel: Channel,
    features: list[str],
    redirect: str,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    """Create a pending flow and return (Google consent URL, expiry)."""
    now = now or datetime.now(UTC)
    if channel.deleted_at is not None or channel.state not in CONNECTABLE_STATES:
        raise OAuthFlowError("CHANNEL_STATE", f"A channel in state {channel.state} cannot be connected.")
    client = client_for(db, channel.id)
    existing = current_connection(db, channel.id)
    scopes = sorted(set(scopes_for(features)) | set(existing.scopes if existing else []))
    db.execute(delete(OAuthPendingFlow).where(OAuthPendingFlow.expires_at < now))
    state, verifier = new_state(), new_verifier()
    sealed = box.seal(
        verifier.encode(),
        purpose="oauth-pkce",
        associated=aad("oauth_pending_flows", "code_verifier_enc", state),
    )
    expires = now + STATE_TTL
    db.add(
        OAuthPendingFlow(
            state=state,
            code_verifier_enc=sealed.ciphertext,
            key_id=sealed.key_id,
            channel_id=channel.id,
            scopes=scopes,
            created_at=now,
            expires_at=expires,
        )
    )
    db.flush()
    params = {
        "client_id": client.client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": code_challenge(verifier),
        "code_challenge_method": "S256",
        "access_type": "offline",
        "include_granted_scopes": "true",
    }
    if existing is None or existing.status != "ACTIVE":
        params["prompt"] = "consent"  # first connect / re-auth: make Google return a refresh token
    return f"{AUTH_URL}?{urlencode(params)}", expires


def _seal_token(box: SecretBox, conn: OAuthConnection, column: str, token: str) -> bytes:
    return box.seal(
        token.encode(), purpose="oauth-token", associated=aad("oauth_connections", column, conn.id)
    ).ciphertext


def _open_token(box: SecretBox, conn: OAuthConnection, column: str, sealed: bytes) -> str:
    return box.open(
        sealed,
        key_id=conn.key_id,
        purpose="oauth-token",
        associated=aad("oauth_connections", column, conn.id),
    ).decode()


def complete_flow(
    db: Session,
    box: SecretBox,
    google: GoogleOAuth,
    youtube: SafeYouTubeClient,
    *,
    state: str,
    code: str | None,
    error: str | None,
    redirect: str,
    now: datetime | None = None,
) -> tuple[Channel, OAuthConnection]:
    """Handle Google's redirect: check and consume state, exchange the code, store tokens."""
    now = now or datetime.now(UTC)
    pending = db.scalar(select(OAuthPendingFlow).where(OAuthPendingFlow.state == state).with_for_update())
    if pending is None:
        security_event(db, "OAUTH_STATE_UNKNOWN", "WARNING", details={"state_len": len(state)})
        raise OAuthFlowError("STATE_INVALID", "This sign-in link is not valid. Start again from TubeForge.")
    db.delete(pending)  # single use, whatever happens next
    db.flush()
    if pending.expires_at <= now:
        raise OAuthFlowError("STATE_EXPIRED", "The sign-in took longer than 10 minutes. Start again.")
    if error or not code:
        raise OAuthFlowError("CONSENT_DENIED", "Google sign-in was cancelled. Nothing was connected.")
    channel = db.get(Channel, pending.channel_id)
    if channel is None or channel.state not in CONNECTABLE_STATES:
        raise OAuthFlowError("CHANNEL_STATE", "This channel can no longer be connected.")
    client = client_for(db, channel.id)
    verifier = box.open(
        pending.code_verifier_enc,
        key_id=pending.key_id,
        purpose="oauth-pkce",
        associated=aad("oauth_pending_flows", "code_verifier_enc", pending.state),
    ).decode()
    tokens = google.exchange(
        client_id=client.client_id,
        client_secret=_client_secret(box, client),
        code=code,
        verifier=verifier,
        redirect=redirect,
    )
    granted = set(tokens.scopes)
    missing = sorted(set(pending.scopes) - granted)
    if missing:
        # Granular consent: the owner un-ticked a box. Give the token back rather than keep a partial grant.
        _try_revoke(google, tokens.access_token)
        names = ", ".join(m.removeprefix(_S) for m in missing)
        raise OAuthFlowError("SCOPE_MISSING", f"Please tick every permission box. Missing: {names}.")

    conn = current_connection(db, channel.id)
    if conn is None or conn.oauth_client_id != client.id:
        if tokens.refresh_token is None:
            raise OAuthFlowError("NO_REFRESH_TOKEN", "Google did not return a long-lived token. Start again.")
        conn = OAuthConnection(
            id=uuid7(),
            channel_id=channel.id,
            oauth_client_id=client.id,
            scopes=[],
            refresh_token_enc=b"",
            key_id=box.key_id,
            status="ACTIVE",
            authorized_at=now,
            created_at=now,
        )
        db.add(conn)
    conn.key_id = box.key_id
    if tokens.refresh_token is not None:
        conn.refresh_token_enc = _seal_token(box, conn, "refresh_token_enc", tokens.refresh_token)
        conn.refresh_expected_expiry = (
            now + TESTING_REFRESH_LIFETIME if client.publishing_status == "TESTING" else None
        )
    elif conn.refresh_token_enc:
        # Incremental consent without a new refresh token: re-seal the old one under the current key.
        old = _open_token(box, conn, "refresh_token_enc", conn.refresh_token_enc)
        conn.refresh_token_enc = _seal_token(box, conn, "refresh_token_enc", old)
    conn.access_token_enc = _seal_token(box, conn, "access_token_enc", tokens.access_token)
    conn.access_token_expires_at = now + timedelta(seconds=tokens.expires_in)
    conn.scopes = sorted(granted | set(conn.scopes))
    conn.status = "ACTIVE"
    conn.last_error = None
    conn.authorized_at = now
    conn.last_authorization_check_at = now
    conn.last_refresh_at = now
    db.flush()

    if channel.state == "NEEDS_REAUTH":
        # Re-authorisation must be the same YouTube channel as before.
        identity = fetch_identity(db, box, google, youtube, channel, now=now)
        if channel.youtube_channel_id and identity["youtube_channel_id"] != channel.youtube_channel_id:
            conn.status = "NEEDS_REAUTH"
            conn.last_error = "re-authorised with a different YouTube channel"
            raise OAuthFlowError("IDENTITY_MISMATCH", "You signed in to a different YouTube channel.")
        back_to = (
            channel.resume_to_state
            if channel.resume_to_state in {"CONNECTED", "ACTIVE", "PAUSED"}
            else "ACTIVE"
        )
        channel.resume_to_state = None
        lifecycle.transition(db, channel, back_to, event="reauthorized", actor=SYSTEM)
    record(
        db,
        actor=SYSTEM,
        action="oauth.connected",
        entity_type="channel",
        entity_id=str(channel.id),
        channel_id=channel.id,
        details={"scopes": [s.removeprefix(_S) for s in conn.scopes], "state": channel.state},
    )
    security_event(db, "OAUTH_CONNECTED", "INFO", channel_id=channel.id)
    db.flush()
    return channel, conn


# --------------------------------------------------------------------------------------- tokens
def mark_needs_reauth(
    db: Session, conn: OAuthConnection, reason: str, *, now: datetime | None = None
) -> None:
    """invalid_grant / 401: stop YouTube work for the channel and tell the owner (CRITICAL)."""
    conn.status = "NEEDS_REAUTH"
    conn.last_error = reason[:500]
    conn.access_token_enc = None
    conn.access_token_expires_at = None
    channel = db.get(Channel, conn.channel_id)
    if channel is not None and channel.state in {"CONNECTED", "ACTIVE", "PAUSED"}:
        channel.resume_to_state = channel.state
        lifecycle.transition(db, channel, "NEEDS_REAUTH", event="token_invalid", actor=SYSTEM, reason=reason)
    security_event(
        db, "OAUTH_NEEDS_REAUTH", "CRITICAL", channel_id=conn.channel_id, details={"reason": reason}
    )
    record(
        db,
        actor=SYSTEM,
        action="oauth.needs_reauth",
        entity_type="channel",
        entity_id=str(conn.channel_id),
        channel_id=conn.channel_id,
        details={"reason": reason},
    )
    notify_owners(
        db,
        event_type="oauth.revoked",
        severity="CRITICAL",
        title="YouTube needs you to sign in again",
        body=f"{channel.name if channel else 'A channel'}: access to YouTube stopped working. "
        "Uploads for this channel are paused until you reconnect.",
        dedup_key=f"oauth.revoked:{conn.id}",
        dedup_window=timedelta(hours=6),
        channel_id=conn.channel_id,
        link=f"/channels/{conn.channel_id}/onboarding",
        now=now,
    )
    db.flush()


def access_token(
    db: Session, box: SecretBox, google: GoogleOAuth, conn: OAuthConnection, *, now: datetime | None = None
) -> str:
    """A valid access token, refreshing when the cached one is (nearly) expired."""
    now = now or datetime.now(UTC)
    if conn.status != "ACTIVE":
        raise YouTubeApiError(ErrorClass.AUTH_EXPIRED, None, None, "connection needs re-authorisation")
    if (
        conn.access_token_enc is not None
        and conn.access_token_expires_at is not None
        and conn.access_token_expires_at > now + ACCESS_TOKEN_MARGIN
    ):
        return _open_token(box, conn, "access_token_enc", conn.access_token_enc)
    client = db.get_one(OAuthClient, conn.oauth_client_id)
    refresh = _open_token(box, conn, "refresh_token_enc", conn.refresh_token_enc)
    try:
        tokens = google.refresh(
            client_id=client.client_id, client_secret=_client_secret(box, client), refresh_token=refresh
        )
    except YouTubeApiError as exc:
        if exc.error_class is ErrorClass.AUTH_EXPIRED:
            mark_needs_reauth(db, conn, exc.reason or exc.detail, now=now)
        else:
            conn.last_error = exc.detail
        raise
    if conn.key_id != box.key_id:
        conn.key_id = box.key_id
        conn.refresh_token_enc = _seal_token(box, conn, "refresh_token_enc", refresh)
    if tokens.refresh_token:  # rotated
        conn.refresh_token_enc = _seal_token(box, conn, "refresh_token_enc", tokens.refresh_token)
    conn.access_token_enc = _seal_token(box, conn, "access_token_enc", tokens.access_token)
    conn.access_token_expires_at = now + timedelta(seconds=tokens.expires_in)
    conn.last_refresh_at = now
    conn.last_error = None
    db.flush()
    return tokens.access_token


def call_context(
    db: Session,
    box: SecretBox,
    google: GoogleOAuth,
    channel: Channel,
    *,
    job_id: str | None = None,
    now: datetime | None = None,
) -> CallContext:
    conn = current_connection(db, channel.id)
    if conn is None:
        raise OAuthFlowError("NOT_CONNECTED", "This channel is not connected to YouTube.")
    client = db.get_one(OAuthClient, conn.oauth_client_id)
    token = access_token(db, box, google, conn, now=now)
    return CallContext(
        db=db, gcp_project=gcp_project(client), access_token=token, channel_id=channel.id, job_id=job_id
    )


# ------------------------------------------------------------------------------------- identity
def fetch_identity(
    db: Session,
    box: SecretBox,
    google: GoogleOAuth,
    youtube: SafeYouTubeClient,
    channel: Channel,
    *,
    now: datetime | None = None,
) -> dict[str, str | None]:
    """The YouTube channel the token belongs to (channels.list mine=true, 1 unit)."""
    item = youtube.my_channel(call_context(db, box, google, channel, now=now))
    snippet: dict[str, Any] = item.get("snippet") or {}
    return {
        "youtube_channel_id": str(item["id"]),
        "title": snippet.get("title"),
        "handle": snippet.get("customUrl"),
    }


def confirm_identity(
    db: Session,
    box: SecretBox,
    google: GoogleOAuth,
    youtube: SafeYouTubeClient,
    channel: Channel,
    youtube_channel_id: str,
    *,
    actor: Actor,
    now: datetime | None = None,
) -> Channel:
    """The owner confirms the connected YouTube channel is the right one → CONNECTED."""
    identity = fetch_identity(db, box, google, youtube, channel, now=now)
    if identity["youtube_channel_id"] != youtube_channel_id:
        raise OAuthFlowError("IDENTITY_MISMATCH", "That is not the channel this sign-in belongs to.")
    other = db.scalar(
        select(Channel.id).where(
            Channel.youtube_channel_id == youtube_channel_id,
            Channel.id != channel.id,
            Channel.deleted_at.is_(None),
        )
    )
    if other is not None:
        raise OAuthFlowError("IDENTITY_IN_USE", "This YouTube channel is already linked to another channel.")
    before = {"state": channel.state, "youtube_channel_id": channel.youtube_channel_id}
    channel.youtube_channel_id = youtube_channel_id
    channel.youtube_handle = identity["handle"]
    if channel.state == "ONBOARDING":
        channel.private_only_mode = True  # every newly connected channel starts private-only
        lifecycle.transition(db, channel, "CONNECTED", event="identity_confirmed", actor=actor)
    lifecycle.mark_step(db, channel.id, "CONNECT")
    record(
        db,
        actor=actor,
        action="oauth.identity_confirmed",
        entity_type="channel",
        entity_id=str(channel.id),
        channel_id=channel.id,
        before=before,
        after={"state": channel.state, "youtube_channel_id": youtube_channel_id},
    )
    db.flush()
    return channel


# ------------------------------------------------------------------------------- health / jobs
@dataclass(frozen=True)
class Health:
    status: str
    scopes: list[str]
    expires_hint: datetime | None
    expiring_soon: bool
    last_refresh_at: datetime | None
    last_error: str | None
    publishing_status: str | None


def health(db: Session, channel_id: uuid.UUID, *, now: datetime | None = None) -> Health:
    now = now or datetime.now(UTC)
    conn = current_connection(db, channel_id)
    if conn is None:
        return Health("NOT_CONNECTED", [], None, False, None, None, None)
    client = db.get(OAuthClient, conn.oauth_client_id)
    expiry = conn.refresh_expected_expiry
    return Health(
        status=conn.status,
        scopes=[s.removeprefix(_S) for s in conn.scopes],
        expires_hint=expiry,
        expiring_soon=expiry is not None and expiry - now < EXPIRY_WARNING,
        last_refresh_at=conn.last_refresh_at,
        last_error=conn.last_error,
        publishing_status=client.publishing_status if client else None,
    )


@dataclass
class TokenHealthResult:
    checked: int = 0
    refreshed: int = 0
    needs_reauth: int = 0
    expiring: int = 0
    errors: int = 0


def token_health(
    db: Session, box: SecretBox, google: GoogleOAuth, *, now: datetime | None = None
) -> TokenHealthResult:
    """Daily job (mnt.token_health): refresh every active token (keeps it in use, §4.4) and warn
    24 h before a Testing-mode refresh token expires."""
    now = now or datetime.now(UTC)
    result = TokenHealthResult()
    conns = db.scalars(
        select(OAuthConnection).where(
            OAuthConnection.status == "ACTIVE", OAuthConnection.revoked_at.is_(None)
        )
    ).all()
    for conn in conns:
        result.checked += 1
        conn.access_token_expires_at = None  # force a refresh: proves the refresh token still works
        try:
            access_token(db, box, google, conn, now=now)
            result.refreshed += 1
        except YouTubeApiError as exc:
            if exc.error_class is ErrorClass.AUTH_EXPIRED:
                result.needs_reauth += 1
            else:
                result.errors += 1
            continue
        if conn.refresh_expected_expiry is not None and conn.refresh_expected_expiry - now < EXPIRY_WARNING:
            result.expiring += 1
            channel = db.get(Channel, conn.channel_id)
            notify_owners(
                db,
                event_type="oauth.expiring",
                severity="WARNING",
                title="YouTube sign-in expires within a day",
                body=f"{channel.name if channel else 'A channel'}: Google's Testing mode ends the sign-in "
                "after 7 days. Reconnect now (about 30 seconds) to keep uploads running.",
                dedup_key=f"oauth.expiring:{conn.id}",
                dedup_window=timedelta(hours=12),
                channel_id=conn.channel_id,
                link=f"/channels/{conn.channel_id}/onboarding",
                now=now,
            )
    db.flush()
    return result


# ----------------------------------------------------------------------------------- disconnect
def _try_revoke(google: GoogleOAuth, token: str) -> bool:
    try:
        google.revoke(token)
        return True
    except YouTubeApiError as exc:
        # 400 invalid_token = already revoked at Google: that is the outcome we want.
        return exc.status == 400


DELETION_SCOPE = [
    "oauth_connections",
    "analytics_snapshots",
    "youtube_api_cache",
    "comment_suggestions",
]


def disconnect(
    db: Session,
    box: SecretBox,
    google: GoogleOAuth,
    channel: Channel,
    *,
    actor: Actor,
    reason: str = "DISCONNECT",
    now: datetime | None = None,
) -> DataDeletionTask:
    """Revoke at Google, delete the token rows, schedule API-data deletion within 7 days (DP-4)."""
    now = now or datetime.now(UTC)
    if not lifecycle.can(channel, "DISCONNECTING"):
        raise OAuthFlowError("CHANNEL_STATE", f"A channel in state {channel.state} cannot be disconnected.")
    revoked: list[bool] = []
    for conn in db.scalars(select(OAuthConnection).where(OAuthConnection.channel_id == channel.id)).all():
        if conn.refresh_token_enc:
            try:
                token = _open_token(box, conn, "refresh_token_enc", conn.refresh_token_enc)
                revoked.append(_try_revoke(google, token))
            except Exception:  # a broken ciphertext must not block the disconnect
                revoked.append(False)
        db.delete(conn)
    db.execute(delete(OAuthPendingFlow).where(OAuthPendingFlow.channel_id == channel.id))
    task = DataDeletionTask(
        id=uuid7(),
        channel_id=channel.id,
        reason=reason,
        scope={"tables": DELETION_SCOPE, "youtube_channel_id": channel.youtube_channel_id},
        due_at=now + timedelta(days=7),
        created_at=now,
    )
    db.add(task)
    before = channel.state
    channel.resume_to_state = None
    lifecycle.transition(db, channel, "DISCONNECTING", event="disconnect", actor=actor)
    record(
        db,
        actor=actor,
        action="oauth.disconnected",
        entity_type="channel",
        entity_id=str(channel.id),
        channel_id=channel.id,
        before={"state": before},
        after={"state": channel.state},
        details={
            "revoked_at_google": all(revoked) if revoked else None,
            "deletion_due": task.due_at.isoformat(),
        },
    )
    security_event(db, "OAUTH_DISCONNECTED", "INFO", channel_id=channel.id)
    if revoked and not all(revoked):
        notify_owners(
            db,
            event_type="oauth.revoke_failed",
            severity="WARNING",
            title="Google did not confirm the disconnect",
            body="TubeForge deleted its copy of the sign-in. To be sure, remove TubeForge at "
            "security.google.com/settings/security/permissions.",
            dedup_key=f"oauth.revoke_failed:{channel.id}",
            channel_id=channel.id,
            now=now,
        )
    db.flush()
    return task
