"""OAuth client registration, YouTube connect flow, identity and token health (BACKEND_SPECIFICATION §2.3).

``/oauth/callback`` is outside ``/api/v1``: Google redirects the owner's browser there. It is public but
only does something for a valid, unexpired, single-use ``state`` (OAUTH_SECURITY §4.2).
"""

from __future__ import annotations

import html
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tubeforge.api.deps import Db, Principal, client_ip, public, request_id, require
from tubeforge.api.errors import ProblemError, not_found, problem_doc
from tubeforge.api.idempotency import Idempotency
from tubeforge.audit import record
from tubeforge.db.models import Channel, OAuthClient, OAuthConnection
from tubeforge.secrets import SecretBox
from tubeforge.youtube import oauth
from tubeforge.youtube.client import SafeYouTubeClient
from tubeforge.youtube.errors import ErrorClass, YouTubeApiError

router = APIRouter(tags=["oauth"])
callback_router = APIRouter(include_in_schema=False)

OAuthManage = Annotated[Principal, Depends(require("oauth.manage"))]
ChannelView = Annotated[Principal, Depends(require("channel.view"))]
GOOGLE: dict[int | str, dict[str, Any]] = {
    409: problem_doc(
        "NO_OAUTH_CLIENT / CHANNEL_STATE / IDENTITY_MISMATCH / IDENTITY_IN_USE / OAUTH_NEEDS_REAUTH"
    ),
    422: problem_doc("IDEMPOTENCY_MISMATCH / UNKNOWN_FEATURE / INVALID_CLIENT_ID"),
    502: problem_doc("GOOGLE_ERROR: Google did not answer as expected (try again)"),
}
Feature = Literal["upload", "readonly", "captions", "playlists", "metadata", "comments", "analytics"]
CLIENT_ID_PATTERN = r"^[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com$"


class OAuthClientIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    client_id: str = Field(pattern=CLIENT_ID_PATTERN, max_length=200)
    client_secret: str | None = Field(default=None, min_length=1, max_length=200, description="Write-only.")
    gcp_project_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
    publishing_status: Literal["TESTING", "IN_PRODUCTION"] = "TESTING"


class OAuthClientOut(BaseModel):
    id: uuid.UUID
    label: str
    client_id: str
    has_secret: bool
    gcp_project_id: str | None
    publishing_status: str
    created_at: datetime


class StartIn(BaseModel):
    channel_id: uuid.UUID
    features: list[Feature] = Field(default_factory=list, max_length=7)


class FeaturesIn(BaseModel):
    features: list[Feature] = Field(min_length=1, max_length=7)


class AuthorizationOut(BaseModel):
    authorization_url: str
    expires_at: datetime


class IdentityOut(BaseModel):
    youtube_channel_id: str
    title: str | None
    handle: str | None


class ConfirmIdentityIn(BaseModel):
    youtube_channel_id: str = Field(pattern=r"^UC[A-Za-z0-9_-]{22}$")


class ChannelConnectionOut(BaseModel):
    id: uuid.UUID
    state: str
    youtube_channel_id: str | None
    youtube_handle: str | None


class HealthOut(BaseModel):
    status: Literal["NOT_CONNECTED", "ACTIVE", "NEEDS_REAUTH", "REVOKED"]
    scopes: list[str]
    expires_hint: datetime | None = Field(description="Testing mode: when Google will end this sign-in.")
    expiring_soon: bool
    last_refresh_at: datetime | None
    last_error: str | None
    publishing_status: str | None


# ---------------------------------------------------------------------------------------- helpers
def _box(request: Request) -> SecretBox:
    box: SecretBox = request.app.state.secret_box
    return box


def _google(request: Request) -> oauth.GoogleOAuth:
    g: oauth.GoogleOAuth = request.app.state.google_oauth
    return g


def _youtube(request: Request) -> SafeYouTubeClient:
    y: SafeYouTubeClient = request.app.state.youtube
    return y


def _redirect(request: Request) -> str:
    return oauth.redirect_uri(request.app.state.settings.port)


def _channel(db: Session, channel_id: uuid.UUID) -> Channel:
    channel = db.get(Channel, channel_id)
    if channel is None or channel.deleted_at is not None:
        raise not_found("No such channel.")
    return channel


def _flow_problem(exc: oauth.OAuthFlowError) -> ProblemError:
    status = 422 if exc.code in {"UNKNOWN_FEATURE", "INVALID_CLIENT_ID"} else 409
    return ProblemError(status, exc.code, "YouTube connection", exc.message)


def _google_problem(db: Session, exc: YouTubeApiError) -> ProblemError:
    db.commit()  # keep NEEDS_REAUTH marks, ledger rows and notifications made before the failure
    if exc.error_class is ErrorClass.AUTH_EXPIRED:
        return ProblemError(409, "OAUTH_NEEDS_REAUTH", "Sign in to YouTube again", "Reconnect this channel.")
    return ProblemError(502, "GOOGLE_ERROR", "Google error", f"{exc.error_class}: {exc.detail}")


def _client_out(row: OAuthClient) -> OAuthClientOut:
    return OAuthClientOut(
        id=row.id,
        label=row.label,
        client_id=row.client_id,
        has_secret=row.client_secret_enc is not None,
        gcp_project_id=row.gcp_project_id,
        publishing_status=row.publishing_status,
        created_at=row.created_at,
    )


def _audit(request: Request, db: Session, p: Principal, action: str, entity_id: str, **details: Any) -> None:
    record(
        db,
        actor=p.actor,
        action=action,
        entity_type="oauth_client",
        entity_id=entity_id,
        details=details,
        request_id=request_id(request),
        ip=client_ip(request),
    )


# ---------------------------------------------------------------------------------------- clients
@router.get("/oauth/clients", response_model=list[OAuthClientOut])
def list_clients(db: Db, _: OAuthManage) -> list[OAuthClientOut]:
    rows = db.scalars(select(OAuthClient).order_by(OAuthClient.created_at.desc())).all()
    return [_client_out(r) for r in rows]


@router.post("/oauth/clients", response_model=OAuthClientOut, status_code=201, responses=GOOGLE)
def add_client(body: OAuthClientIn, request: Request, db: Db, p: OAuthManage) -> Any:
    idem = Idempotency(db, request, p.user.id, body.model_dump(exclude={"client_secret"}))
    if (replayed := idem.replay()) is not None:
        return replayed
    try:
        row = oauth.register_client(
            db,
            _box(request),
            label=body.label,
            client_id=body.client_id,
            client_secret=body.client_secret,
            gcp_project_id=body.gcp_project_id,
            publishing_status=body.publishing_status,
        )
    except oauth.OAuthFlowError as exc:
        raise _flow_problem(exc) from exc
    db.refresh(row)
    _audit(request, db, p, "oauth.client_added", str(row.id), client_id=row.client_id)
    out = _client_out(row)
    idem.store(201, out.model_dump(mode="json"))
    db.commit()
    return out


@router.delete("/oauth/clients/{client_id}", status_code=204, responses=GOOGLE)
def delete_client(client_id: uuid.UUID, request: Request, db: Db, p: OAuthManage) -> Response:
    row = db.get(OAuthClient, client_id)
    if row is None:
        raise not_found("No such OAuth client.")
    used = db.scalar(
        select(func.count()).select_from(OAuthConnection).where(OAuthConnection.oauth_client_id == client_id)
    )
    if used:
        raise ProblemError(
            409, "CLIENT_IN_USE", "Client in use", "Disconnect the channels that use it first."
        )
    db.delete(row)
    _audit(request, db, p, "oauth.client_deleted", str(client_id))
    db.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------------------------------ flow
def _start(
    request: Request, db: Session, p: Principal, channel_id: uuid.UUID, features: list[str], body: Any
) -> Any:
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    channel = _channel(db, channel_id)
    try:
        url, expires = oauth.start_flow(
            db, _box(request), channel=channel, features=list(features), redirect=_redirect(request)
        )
    except oauth.OAuthFlowError as exc:
        raise _flow_problem(exc) from exc
    out = AuthorizationOut(authorization_url=url, expires_at=expires)
    record(
        db,
        actor=p.actor,
        action="oauth.flow_started",
        entity_type="channel",
        entity_id=str(channel.id),
        channel_id=channel.id,
        details={"features": sorted(features)},
        request_id=request_id(request),
        ip=client_ip(request),
    )
    idem.store(200, out.model_dump(mode="json"))
    db.commit()
    return out


@router.post("/oauth/youtube/start", response_model=AuthorizationOut, responses=GOOGLE)
def start(body: StartIn, request: Request, db: Db, p: OAuthManage) -> Any:
    return _start(request, db, p, body.channel_id, list(body.features), body)


@router.post("/channels/{channel_id}/oauth/incremental", response_model=AuthorizationOut, responses=GOOGLE)
def incremental(channel_id: uuid.UUID, body: FeaturesIn, request: Request, db: Db, p: OAuthManage) -> Any:
    return _start(request, db, p, channel_id, list(body.features), body)


@router.get("/channels/{channel_id}/oauth/identity", response_model=IdentityOut, responses=GOOGLE)
def identity(channel_id: uuid.UUID, request: Request, db: Db, _: OAuthManage) -> IdentityOut:
    channel = _channel(db, channel_id)
    try:
        found = oauth.fetch_identity(db, _box(request), _google(request), _youtube(request), channel)
    except oauth.OAuthFlowError as exc:
        raise _flow_problem(exc) from exc
    except YouTubeApiError as exc:
        raise _google_problem(db, exc) from exc
    db.commit()  # quota ledger row
    return IdentityOut(
        youtube_channel_id=str(found["youtube_channel_id"]), title=found["title"], handle=found["handle"]
    )


@router.post(
    "/channels/{channel_id}/oauth/confirm-identity", response_model=ChannelConnectionOut, responses=GOOGLE
)
def confirm(channel_id: uuid.UUID, body: ConfirmIdentityIn, request: Request, db: Db, p: OAuthManage) -> Any:
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    channel = _channel(db, channel_id)
    try:
        oauth.confirm_identity(
            db,
            _box(request),
            _google(request),
            _youtube(request),
            channel,
            body.youtube_channel_id,
            actor=p.actor,
        )
    except oauth.OAuthFlowError as exc:
        db.commit()
        raise _flow_problem(exc) from exc
    except YouTubeApiError as exc:
        raise _google_problem(db, exc) from exc
    out = ChannelConnectionOut(
        id=channel.id,
        state=channel.state,
        youtube_channel_id=channel.youtube_channel_id,
        youtube_handle=channel.youtube_handle,
    )
    idem.store(200, out.model_dump(mode="json"))
    db.commit()
    return out


@router.get("/channels/{channel_id}/oauth/health", response_model=HealthOut)
def oauth_health(channel_id: uuid.UUID, db: Db, _: ChannelView) -> HealthOut:
    _channel(db, channel_id)
    h = oauth.health(db, channel_id)
    return HealthOut(**h.__dict__)


# -------------------------------------------------------------------------------------- callback
_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>TubeForge — {title}</title>
<style>body{{font-family:system-ui,sans-serif;background:#0f0d1a;color:#ece9f6;display:grid;place-items:center;
min-height:100vh;margin:0}}main{{max-width:28rem;padding:2rem;border-radius:1rem;background:#1b1830;
border:1px solid #2e2a4a}}h1{{font-size:1.25rem}}a{{color:#c4b5fd}}</style></head>
<body><main><h1>{title}</h1><p>{message}</p>
<p><a href="{link}">Return to TubeForge</a></p></main></body></html>"""


def _page(status: int, title: str, message: str, link: str) -> HTMLResponse:
    body = _PAGE.format(title=html.escape(title), message=html.escape(message), link=html.escape(link))
    return HTMLResponse(
        body,
        status_code=status,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",  # the code and state must not leak to other sites
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
        },
    )


@callback_router.get("/oauth/callback", dependencies=[Depends(public)])
def callback(
    request: Request,
    db: Db,
    state: Annotated[str, Query(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]{43}$")],
    code: Annotated[str | None, Query(max_length=2048)] = None,
    error: Annotated[str | None, Query(max_length=200)] = None,
) -> HTMLResponse:
    try:
        channel, _ = oauth.complete_flow(
            db,
            _box(request),
            _google(request),
            _youtube(request),
            state=state,
            code=code,
            error=error,
            redirect=_redirect(request),
        )
    except oauth.OAuthFlowError as exc:
        db.commit()  # the consumed state and any security event stay recorded
        return _page(400, "Not connected", exc.message, "/channels")
    except YouTubeApiError as exc:
        db.commit()
        return _page(
            502, "Not connected", f"Google did not accept the sign-in ({exc.error_class}).", "/channels"
        )
    db.commit()
    link = f"/channels/{channel.id}/onboarding"
    if channel.state == "ONBOARDING":
        return _page(
            200, "Connected to Google", "Go back to TubeForge and confirm it is the right channel.", link
        )
    return _page(200, "Connected to Google", "YouTube access is working again for this channel.", link)
