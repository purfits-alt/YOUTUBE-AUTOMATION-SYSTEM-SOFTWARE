"""Owner-initiated single-item lookups (A04; CHANNEL_DISCOVERY_SPEC §7, YOUTUBE_API_INTEGRATION §10).

Compliance-first (ADR-0015, DP-1/DP-2):

- Only the owner starts a lookup, for **one** channel or **one** video, or one search showing at most
  10 results. There are no background lookups, no batch lookups and no follow-up calls (a search
  shows the search snippets only, not each result's statistics).
- Only the public fields the spec lists are kept: title, published date, view count as of the
  fetch, duration, a 300-character description excerpt, channel name and subscriber count when
  public. Everything else Google returns is dropped before storage.
- Results are cached in ``youtube_api_cache`` for at most 30 days and purged hourly
  (``mnt.retention.purge_api_cache``). Nothing here combines items, ranks them or feeds scores;
  the static check in ``tests/unit/test_discovery_rules.py`` enforces that no module both reads
  this data and writes score tables.
- Every call is metered in the quota ledger. Searches use the SEARCH bucket.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from tubeforge.db.ids import uuid7
from tubeforge.db.models import YoutubeApiCache
from tubeforge.youtube import quota
from tubeforge.youtube.client import API_BASE, CallContext, SafeYouTubeClient

Kind = Literal["CHANNEL", "VIDEO", "SEARCH"]
CACHE_TTL = timedelta(days=30)
MAX_SEARCH_RESULTS = 10
EXCERPT = 300
NOTICE = "Public info about one channel or video — not combined with others. Kept for 30 days at most."
CHANNEL_ID = re.compile(r"^UC[\w-]{22}$")
HANDLE = re.compile(r"^@?([\w.\-]{3,30})$")
VIDEO_ID = re.compile(r"^[\w-]{11}$")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
METHOD: dict[str, str] = {"CHANNEL": "channels.list", "VIDEO": "videos.list", "SEARCH": "search.list"}


class YouTubeLookupError(Exception):
    def __init__(self, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


@dataclass(frozen=True)
class Query:
    kind: Kind
    key: str  # cache key: "id:UC…", "handle:@name", "video:abc…", "q:normalised text"
    params: dict[str, str]


@dataclass(frozen=True)
class LookupResult:
    kind: Kind
    query_key: str
    items: list[dict[str, Any]]
    fetched_at: datetime
    expires_at: datetime
    cached: bool
    cache_id: uuid.UUID


def _from_url(text: str) -> tuple[str, str] | None:
    """('channel'|'handle'|'video', value) from a YouTube link. The link is only parsed, never opened."""
    if "://" not in text:
        return None
    u = urlparse(text)
    host = (u.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        raise YouTubeLookupError("INVALID_QUERY", "Only youtube.com or youtu.be links can be looked up.")
    parts = [p for p in u.path.split("/") if p]
    if host == "youtu.be" and parts:
        return ("video", parts[0])
    if parts[:1] == ["watch"]:
        v = parse_qs(u.query).get("v", [""])[0]
        return ("video", v)
    if parts[:1] in (["shorts"], ["live"]) and len(parts) > 1:
        return ("video", parts[1])
    if parts[:1] == ["channel"] and len(parts) > 1:
        return ("channel", parts[1])
    if parts and parts[0].startswith("@"):
        return ("handle", parts[0])
    raise YouTubeLookupError("INVALID_QUERY", "That YouTube link is not a channel or video address.")


def parse_query(kind: Kind, raw: str) -> Query:
    text = raw.strip()
    if not text or len(text) > 200:
        raise YouTubeLookupError(
            "INVALID_QUERY", "Enter a channel, video or search text (at most 200 characters)."
        )
    link = _from_url(text)
    if kind == "SEARCH":
        if link is not None:
            raise YouTubeLookupError("INVALID_QUERY", "Use Channel or Video for links; Search is for words.")
        words = " ".join(text.split())
        if len(words) < 2 or len(words) > 100:
            raise YouTubeLookupError("INVALID_QUERY", "Search text must be 2–100 characters.")
        return Query(
            "SEARCH",
            f"q:{words.lower()}",
            {"part": "snippet", "q": words, "maxResults": str(MAX_SEARCH_RESULTS),
             "type": "video,channel", "safeSearch": "moderate"},
        )  # fmt: skip
    if kind == "VIDEO":
        value = link[1] if link and link[0] == "video" else text
        if link and link[0] != "video":
            raise YouTubeLookupError("INVALID_QUERY", "That link is a channel; choose Channel.")
        if not VIDEO_ID.match(value):
            raise YouTubeLookupError("INVALID_QUERY", "A video ID has 11 letters, digits, '-' or '_'.")
        return Query("VIDEO", f"video:{value}", {"part": "snippet,statistics,contentDetails", "id": value})
    value = link[1] if link else text
    if link and link[0] == "video":
        raise YouTubeLookupError("INVALID_QUERY", "That link is a video; choose Video.")
    if CHANNEL_ID.match(value):
        return Query("CHANNEL", f"id:{value}", {"part": "snippet,statistics", "id": value})
    m = HANDLE.match(value)
    if m:
        handle = "@" + m.group(1)
        return Query(
            "CHANNEL", f"handle:{handle.lower()}", {"part": "snippet,statistics", "forHandle": handle}
        )
    raise YouTubeLookupError("INVALID_QUERY", "Enter a channel ID (UC…), a @handle or a channel link.")


def _excerpt(text: Any) -> str:
    return str(text or "")[:EXCERPT]


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def shape(kind: Kind, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep only the public fields the spec allows (§7); drop the rest before storage."""
    out: list[dict[str, Any]] = []
    for item in (payload.get("items") or [])[: MAX_SEARCH_RESULTS if kind == "SEARCH" else 1]:
        sn = item.get("snippet") or {}
        if kind == "CHANNEL":
            st = item.get("statistics") or {}
            out.append(
                {
                    "type": "channel",
                    "channel_id": item.get("id"),
                    "title": sn.get("title"),
                    "handle": sn.get("customUrl"),
                    "published_at": sn.get("publishedAt"),
                    "description_excerpt": _excerpt(sn.get("description")),
                    "subscriber_count": None
                    if st.get("hiddenSubscriberCount")
                    else _int(st.get("subscriberCount")),
                    "video_count": _int(st.get("videoCount")),
                    "view_count": _int(st.get("viewCount")),
                }
            )
        elif kind == "VIDEO":
            st = item.get("statistics") or {}
            out.append(
                {
                    "type": "video",
                    "video_id": item.get("id"),
                    "title": sn.get("title"),
                    "channel_title": sn.get("channelTitle"),
                    "published_at": sn.get("publishedAt"),
                    "duration": (item.get("contentDetails") or {}).get("duration"),
                    "description_excerpt": _excerpt(sn.get("description")),
                    "view_count": _int(st.get("viewCount")),
                }
            )
        else:
            ident = item.get("id") or {}
            out.append(
                {
                    "type": "video" if ident.get("kind") == "youtube#video" else "channel",
                    "video_id": ident.get("videoId"),
                    "channel_id": ident.get("channelId") or sn.get("channelId"),
                    "title": sn.get("title"),
                    "channel_title": sn.get("channelTitle"),
                    "published_at": sn.get("publishedAt"),
                    "description_excerpt": _excerpt(sn.get("description")),
                }
            )
    return out


def cached(db: Session, kind: Kind, key: str, now: datetime) -> YoutubeApiCache | None:
    return db.scalar(
        select(YoutubeApiCache).where(
            YoutubeApiCache.lookup_kind == kind,
            YoutubeApiCache.query_key == key,
            YoutubeApiCache.expires_at > now,
        )
    )


def lookup(
    db: Session,
    client: SafeYouTubeClient,
    ctx: CallContext,
    *,
    kind: Kind,
    query: str,
    requested_by: uuid.UUID,
    now: datetime | None = None,
) -> LookupResult:
    """One lookup. A fresh cache entry answers without calling YouTube (and without quota)."""
    now = now or datetime.now(UTC)
    q = parse_query(kind, query)
    hit = cached(db, q.kind, q.key, now)
    if hit is not None:
        items = list(hit.response.get("items", []))
        return LookupResult(q.kind, q.key, items, hit.fetched_at, hit.expires_at, True, hit.id)
    method = METHOD[q.kind]
    try:
        ctx.reservation = quota.reserve(
            db, project=ctx.gcp_project, method=method, purpose="owner_lookup", now=now
        )
    except quota.QuotaExhausted as exc:
        raise YouTubeLookupError(
            "WAITING_QUOTA",
            "Today's YouTube quota for this kind of lookup is used up.",
            resets_at=exc.resets_at,
        ) from exc
    try:
        resp = client.request(ctx, method, "GET", f"{API_BASE}/{method.split('.')[0]}", params=q.params)
    except Exception:
        if ctx.reservation is not None and ctx.reservation.state == "HELD":
            quota.release(db, ctx.reservation)
        raise
    items = shape(q.kind, resp.json())
    if not items:
        raise YouTubeLookupError("NOT_FOUND", "YouTube has no public channel or video for that.")
    expires = now + CACHE_TTL
    db.execute(
        insert(YoutubeApiCache)
        .values(
            id=uuid7(),
            requested_by=requested_by,
            lookup_kind=q.kind,
            query_key=q.key,
            response={"items": items},
            fetched_at=now,
            expires_at=expires,
        )
        .on_conflict_do_update(
            index_elements=["lookup_kind", "query_key"],
            set_={
                "response": {"items": items},
                "fetched_at": now,
                "expires_at": expires,
                "requested_by": requested_by,
            },
        )
    )
    row = db.scalar(
        select(YoutubeApiCache)
        .where(YoutubeApiCache.lookup_kind == q.kind, YoutubeApiCache.query_key == q.key)
        .execution_options(populate_existing=True)
    )
    assert row is not None
    return LookupResult(q.kind, q.key, items, now, expires, False, row.id)


def recent(db: Session, *, now: datetime | None = None, limit: int = 20) -> list[YoutubeApiCache]:
    """The latest lookups, newest first — each shown on its own, never combined."""
    now = now or datetime.now(UTC)
    return list(
        db.scalars(
            select(YoutubeApiCache)
            .where(YoutubeApiCache.expires_at > now)
            .order_by(YoutubeApiCache.fetched_at.desc())
            .limit(limit)
        )
    )
