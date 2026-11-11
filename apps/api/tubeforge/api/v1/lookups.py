"""Competitor lookup — one public channel or video at a time (BACKEND_SPECIFICATION §4.5,
CHANNEL_DISCOVERY_SPEC §7, ADR-0015).

The owner starts each lookup. The answer shows that one item's public metadata, with the notice
"not combined with others"; nothing is ranked, averaged or fed into scores. Results are cached for
at most 30 days. A cached answer needs no token and costs no quota. The call uses the owner's own
connected channel (read-only scope) and is metered in the quota ledger.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.api.deps import Db, Principal, client_ip, request_id, require
from tubeforge.api.errors import ProblemError, problem_doc
from tubeforge.api.idempotency import Idempotency
from tubeforge.audit import record
from tubeforge.db.models import Channel, OAuthConnection, YoutubeApiCache
from tubeforge.orchestrator.controls import stop_reason
from tubeforge.youtube import lookup, oauth
from tubeforge.youtube.errors import ErrorClass, YouTubeApiError

router = APIRouter(tags=["research"])
Lookup = Annotated[Principal, Depends(require("research.lookup"))]
WRITE: dict[int | str, dict[str, Any]] = {
    404: problem_doc("NOT_FOUND_ON_YOUTUBE"),
    409: problem_doc("STOPPED / NO_CONNECTED_CHANNEL / NEEDS_REAUTH / WAITING_QUOTA"),
    422: problem_doc("INVALID_QUERY / IDEMPOTENCY_MISMATCH"),
    502: problem_doc("YOUTUBE_ERROR"),
}


class LookupIn(BaseModel):
    kind: Literal["CHANNEL", "VIDEO", "SEARCH"]
    query: str = Field(min_length=2, max_length=200)
    channel_id: uuid.UUID | None = Field(
        default=None, description="Which of your connected channels makes the call (default: the first one)."
    )


class LookupItem(BaseModel):
    type: Literal["channel", "video"]
    title: str | None = None
    channel_id: str | None = None
    video_id: str | None = None
    handle: str | None = None
    channel_title: str | None = None
    published_at: str | None = None
    duration: str | None = None
    description_excerpt: str = ""
    subscriber_count: int | None = None
    video_count: int | None = None
    view_count: int | None = None


class LookupOut(BaseModel):
    id: uuid.UUID
    kind: Literal["CHANNEL", "VIDEO", "SEARCH"]
    query_key: str
    items: list[LookupItem]
    cached: bool
    fetched_at: datetime
    expires_at: datetime
    notice: str = lookup.NOTICE


def _out(row_id: uuid.UUID, kind: str, key: str, items: list[dict[str, Any]], cached: bool,
         fetched: datetime, expires: datetime) -> LookupOut:  # fmt: skip
    return LookupOut(
        id=row_id,
        kind=kind,
        query_key=key,
        items=[LookupItem(**i) for i in items],
        cached=cached,
        fetched_at=fetched,
        expires_at=expires,
    )


def _caller(db: Session, channel_id: uuid.UUID | None) -> Channel:
    stmt = (
        select(Channel)
        .join(OAuthConnection, OAuthConnection.channel_id == Channel.id)
        .where(OAuthConnection.status == "ACTIVE", Channel.deleted_at.is_(None))
        .order_by(Channel.created_at)
    )
    if channel_id is not None:
        stmt = stmt.where(Channel.id == channel_id)
    channel = db.scalars(stmt.limit(1)).first()
    if channel is None:
        raise ProblemError(
            409,
            "NO_CONNECTED_CHANNEL",
            "Connect a channel first",
            "Lookups use your own connected channel's read-only access. Connect one in Channels.",
        )
    return channel


@router.post("/lookups/youtube", response_model=LookupOut, responses=WRITE)
def run_lookup(body: LookupIn, request: Request, db: Db, p: Lookup) -> Any:
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    try:
        q = lookup.parse_query(body.kind, body.query)
    except lookup.YouTubeLookupError as exc:
        raise ProblemError(422, exc.code, "Not a valid lookup", exc.message) from exc
    hit = lookup.cached(db, q.kind, q.key, datetime.now(UTC))
    if hit is not None:
        out = _out(hit.id, q.kind, q.key, hit.response.get("items", []), True, hit.fetched_at, hit.expires_at)
    else:
        if stop_reason(db) is not None:
            raise ProblemError(
                409, "STOPPED", "Emergency Stop is on", "Clear Emergency Stop to look things up."
            )
        channel = _caller(db, body.channel_id)
        try:
            ctx = oauth.call_context(
                db, request.app.state.secret_box, request.app.state.google_oauth, channel
            )
            result = lookup.lookup(
                db, request.app.state.youtube, ctx, kind=body.kind, query=body.query, requested_by=p.user.id
            )
        except oauth.OAuthFlowError as exc:
            db.commit()
            raise ProblemError(409, "NO_CONNECTED_CHANNEL", "Not connected", exc.message) from exc
        except lookup.YouTubeLookupError as exc:
            db.commit()  # keep the quota ledger: Google counts the call even when nothing is found
            status, code = {
                "NOT_FOUND": (404, "NOT_FOUND_ON_YOUTUBE"),
                "WAITING_QUOTA": (409, "WAITING_QUOTA"),
            }.get(exc.code, (422, exc.code))
            extra = {"resets_at": exc.extra["resets_at"].isoformat()} if "resets_at" in exc.extra else {}
            raise ProblemError(status, code, "Lookup not possible", exc.message, **extra) from exc
        except YouTubeApiError as exc:
            db.commit()
            if exc.error_class is ErrorClass.AUTH_EXPIRED:
                raise ProblemError(
                    409, "NEEDS_REAUTH", "Sign in again", "Reconnect your channel, then retry."
                ) from exc
            if exc.error_class is ErrorClass.QUOTA_EXCEEDED:
                raise ProblemError(
                    409, "WAITING_QUOTA", "Quota used up", "Try again after the quota reset."
                ) from exc
            raise ProblemError(502, "YOUTUBE_ERROR", "YouTube error", exc.detail or str(exc)) from exc
        out = _out(result.cache_id, result.kind, result.query_key, result.items, False, result.fetched_at,
                   result.expires_at)  # fmt: skip
    record(
        db,
        actor=p.actor,
        action="youtube.lookup",
        entity_type="youtube_lookup",
        entity_id=str(out.id),
        details={"kind": out.kind, "query_key": out.query_key, "cached": out.cached},
        request_id=request_id(request),
        ip=client_ip(request),
    )
    idem.store(200, out.model_dump(mode="json"))
    db.commit()
    return out


@router.get("/lookups/youtube", response_model=list[LookupOut])
def recent_lookups(db: Db, p: Lookup, limit: Annotated[int, Query(ge=1, le=50)] = 20) -> list[LookupOut]:
    """Recent lookups, newest first. Each is its own result; nothing is combined or ranked."""
    rows: list[YoutubeApiCache] = lookup.recent(db, limit=limit)
    return [
        _out(r.id, r.lookup_kind, r.query_key, r.response.get("items", []), True, r.fetched_at, r.expires_at)
        for r in rows
    ]
