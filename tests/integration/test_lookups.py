"""Competitor lookup A04: one item, 30-day cache, quota, no aggregation (CHANNEL_DISCOVERY_SPEC §7)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tests.integration.conftest import BASE_URL, Env, login
from tests.integration.test_channels_and_upload import FakeYouTube, World
from tests.integration.test_oauth_flow import CLIENT_ID
from tubeforge.db.models import QuotaLedger, YoutubeApiCache
from tubeforge.main import create_app
from tubeforge.youtube import lookup, oauth, retention
from tubeforge.youtube.client import SafeYouTubeClient

pytestmark = pytest.mark.integration
OTHER = "UCabcdefghijklmnopqrstuv"
LOOKUP = "/api/v1/lookups/youtube"


@dataclass
class LookupYouTube(FakeYouTube):
    reads: list[httpx.Request] = field(default_factory=list)

    def __call__(self, req: httpx.Request) -> httpx.Response:
        p = req.url.params
        if req.url.path == "/youtube/v3/channels" and ("id" in p or "forHandle" in p):
            self.reads.append(req)
            if p.get("id") == "UCnotthereaaaaaaaaaaaaaa":
                return httpx.Response(200, json={"items": []})
            return httpx.Response(200, json={"items": [{
                "id": OTHER,
                "snippet": {"title": "Budget Bros", "customUrl": "@budgetbros",
                            "publishedAt": "2020-01-01T00:00:00Z",
                            "description": "x" * 900, "thumbnails": {"default": {"url": "https://i.ytimg.com/a"}},
                            "country": "US"},
                "statistics": {"subscriberCount": "12000", "videoCount": "90", "viewCount": "1500000",
                               "hiddenSubscriberCount": False},
                "brandingSettings": {"channel": {"keywords": "secret strategy"}},
            }]})  # fmt: skip
        if req.url.path == "/youtube/v3/videos" and "statistics" in p.get("part", ""):
            self.reads.append(req)
            return httpx.Response(200, json={"items": [{
                "id": p["id"],
                "snippet": {"title": "Student budget in Excel", "channelTitle": "Budget Bros",
                            "publishedAt": "2026-10-01T00:00:00Z", "description": "How I budget",
                            "tags": ["a"]},
                "statistics": {"viewCount": "3456", "likeCount": "100", "commentCount": "9"},
                "contentDetails": {"duration": "PT9M30S"},
            }]})  # fmt: skip
        if req.url.path == "/youtube/v3/search":
            self.reads.append(req)
            items = [
                {"id": {"kind": "youtube#video", "videoId": f"vid{n:08d}"},
                 "snippet": {"title": f"Result {n}", "channelTitle": "Some channel", "channelId": OTHER,
                             "publishedAt": "2026-01-01T00:00:00Z", "description": "d"}}
                for n in range(int(p["maxResults"]) + 5)
            ]  # fmt: skip
            return httpx.Response(200, json={"items": items})
        if req.url.path == "/youtube/v3/channels" and p.get("forHandle") is None and p.get("mine") is None:
            return httpx.Response(400)
        return super().__call__(req)


@pytest.fixture
def world(env: Env) -> Iterator[World]:
    yt = LookupYouTube()
    app = create_app(env.app_settings)
    app.state.google_oauth = oauth.GoogleOAuth(transport=httpx.MockTransport(yt))
    app.state.youtube = SafeYouTubeClient(transport=httpx.MockTransport(yt))
    with TestClient(app, base_url=BASE_URL) as client:
        w = World(env, client, login(client), yt, app)
        r = w.post(
            "/api/v1/oauth/clients",
            {"label": "Desktop", "client_id": CLIENT_ID, "client_secret": "s3cret-value"},
        )
        assert r.status_code == 201
        yield w


def test_parse_query_accepts_ids_handles_and_links_only() -> None:
    assert lookup.parse_query("CHANNEL", OTHER).key == f"id:{OTHER}"
    assert lookup.parse_query("CHANNEL", "@BudgetBros").params["forHandle"] == "@BudgetBros"
    assert lookup.parse_query("CHANNEL", "https://www.youtube.com/@BudgetBros").key == "handle:@budgetbros"
    assert lookup.parse_query("CHANNEL", f"https://youtube.com/channel/{OTHER}").key == f"id:{OTHER}"
    assert lookup.parse_query("VIDEO", "https://youtu.be/dQw4w9WgXcQ").key == "video:dQw4w9WgXcQ"
    assert (
        lookup.parse_query("VIDEO", "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1").key
        == "video:dQw4w9WgXcQ"
    )
    assert (
        lookup.parse_query("VIDEO", "https://www.youtube.com/shorts/dQw4w9WgXcQ").key == "video:dQw4w9WgXcQ"
    )
    assert lookup.parse_query("SEARCH", "  Student   Budget ").key == "q:student budget"
    for kind, bad in (
        ("CHANNEL", "https://evil.example.com/@x"),
        ("CHANNEL", "https://youtu.be/dQw4w9WgXcQ"),
        ("VIDEO", "abc"),
        ("SEARCH", "https://www.youtube.com/@x"),
        ("CHANNEL", "a b c"),
    ):
        with pytest.raises(lookup.YouTubeLookupError):
            lookup.parse_query(kind, bad)  # type: ignore[arg-type]


def test_lookup_needs_a_connected_channel(world: World) -> None:
    r = world.post(LOOKUP, {"kind": "CHANNEL", "query": OTHER})
    assert (r.status_code, r.json()["code"]) == (409, "NO_CONNECTED_CHANNEL")
    assert world.yt.reads == []


def test_channel_video_search_are_single_item_cached_and_metered(world: World) -> None:
    world.connect(world.new_channel())
    r = world.post(LOOKUP, {"kind": "CHANNEL", "query": "@BudgetBros"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cached"] is False and body["notice"].startswith("Public info about one channel or video")
    (item,) = body["items"]
    assert item == {
        "type": "channel", "title": "Budget Bros", "channel_id": OTHER, "video_id": None,
        "handle": "@budgetbros",
        "channel_title": None, "published_at": "2020-01-01T00:00:00Z", "duration": None,
        "description_excerpt": "x" * 300, "subscriber_count": 12000, "video_count": 90, "view_count": 1500000,
    }  # fmt: skip
    # only allowed public fields are stored (no thumbnails, country, keywords)
    with world.db() as db:
        row = db.scalars(select(YoutubeApiCache)).one()
        stored = str(row.response)
        assert "secret strategy" not in stored and "ytimg" not in stored and "country" not in stored
        assert row.expires_at - row.fetched_at == timedelta(days=30)
    again = world.post(LOOKUP, {"kind": "CHANNEL", "query": "https://www.youtube.com/@budgetbros"})
    assert again.json()["cached"] is True and len(world.yt.reads) == 1  # cache: no second call

    v = world.post(LOOKUP, {"kind": "VIDEO", "query": "https://youtu.be/dQw4w9WgXcQ"}).json()
    assert v["items"][0]["view_count"] == 3456 and v["items"][0]["duration"] == "PT9M30S"
    assert "likeCount" not in str(v) and "tags" not in str(v)
    s = world.post(LOOKUP, {"kind": "SEARCH", "query": "student budget"}).json()
    assert len(s["items"]) == 10 and all(i["view_count"] is None for i in s["items"])  # snippets only
    assert [r.url.path for r in world.yt.reads] == [
        "/youtube/v3/channels",
        "/youtube/v3/videos",
        "/youtube/v3/search",
    ]
    assert world.yt.reads[2].url.params["maxResults"] == "10"

    missing = world.post(LOOKUP, {"kind": "CHANNEL", "query": "UCnotthereaaaaaaaaaaaaaa"})
    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND_ON_YOUTUBE")
    with world.db() as db:
        methods = [m for (m,) in db.execute(select(QuotaLedger.method).order_by(QuotaLedger.occurred_at))]
        assert methods[-4:] == [
            "channels.list",
            "videos.list",
            "search.list",
            "channels.list",
        ]  # failed one too
        buckets = {
            b for (b,) in db.execute(select(QuotaLedger.bucket).where(QuotaLedger.method == "search.list"))
        }
        assert buckets == {"SEARCH"}

    recent = world.client.get(LOOKUP).json()
    assert [x["kind"] for x in recent] == ["SEARCH", "VIDEO", "CHANNEL"] and all(x["cached"] for x in recent)
    actions = world.env.sql("SELECT details->>'kind' FROM audit_log WHERE action = 'youtube.lookup'")
    assert len(actions) == 4  # successful lookups (the not-found one is in the quota ledger)


def test_expired_lookups_are_purged_and_refetched(world: World) -> None:
    world.connect(world.new_channel())
    world.post(LOOKUP, {"kind": "CHANNEL", "query": OTHER})
    world.env.sql("UPDATE youtube_api_cache SET fetched_at = now() - interval '31 days', "
                  "expires_at = now() - interval '1 day'")  # fmt: skip
    assert world.client.get(LOOKUP).json() == []  # expired entries are never shown
    again = world.post(LOOKUP, {"kind": "CHANNEL", "query": OTHER})
    assert again.json()["cached"] is False and len(world.yt.reads) == 2
    world.env.sql("UPDATE youtube_api_cache SET fetched_at = now() - interval '31 days', "
                  "expires_at = now() - interval '1 day'")  # fmt: skip
    with world.db() as db:
        assert retention.purge_api_cache(db) == 1
        db.commit()
        assert db.scalar(select(func.count()).select_from(YoutubeApiCache)) == 0


def test_cache_cannot_hold_data_longer_than_30_days(env: Env) -> None:
    with pytest.raises(Exception, match="check"):
        env.sql(
            "INSERT INTO youtube_api_cache (id, requested_by, lookup_kind, query_key, response, fetched_at, "
            "expires_at) VALUES (:id, :u, 'CHANNEL', 'k', '{}', now(), now() + interval '31 days')",
            id=uuid.uuid4(),
            u=env.owner.id,
        )


def test_emergency_stop_and_quota(world: World) -> None:
    world.connect(world.new_channel())
    world.env.sql("UPDATE system_settings SET emergency_stop = true")
    r = world.post(LOOKUP, {"kind": "VIDEO", "query": "dQw4w9WgXcQ"})
    assert (r.status_code, r.json()["code"]) == (409, "STOPPED")
    world.env.sql("UPDATE system_settings SET emergency_stop = false")
    world.env.sql("UPDATE quota_config SET daily_limit = 0 WHERE bucket = 'SEARCH'")
    r = world.post(LOOKUP, {"kind": "SEARCH", "query": "budget tips"})
    assert (r.status_code, r.json()["code"]) == (409, "WAITING_QUOTA") and "resets_at" in r.json()
    assert world.yt.reads == []
    bad = world.post(LOOKUP, {"kind": "VIDEO", "query": "abc"})
    assert (bad.status_code, bad.json()["code"]) == (422, "INVALID_QUERY")


def test_viewer_cannot_look_up(env: Env, add_user) -> None:  # type: ignore[no-untyped-def]
    add_user("viewer3@example.com", "VIEWER")
    with env.client() as client:
        h = login(client, "viewer3@example.com")
        r = client.post(LOOKUP, json={"kind": "VIDEO", "query": "dQw4w9WgXcQ"},
                        headers={**h, "Idempotency-Key": str(uuid.uuid4())})  # fmt: skip
        assert r.status_code == 403
