"""Research sources: registry, Wikipedia pageviews, RSS, API, Emergency Stop, retention (P6-A)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from tests.integration.conftest import OWNER_PASSWORD, Env, login
from tests.unit.test_research_fetcher import RSS, resolver
from tubeforge.db.models import ResearchSource, SourceDocument, SystemSettings
from tubeforge.main import create_app
from tubeforge.research import rss, trends, wikipedia
from tubeforge.research.fetcher import ResearchFetcher
from tubeforge.research.sources import SourceUnavailableError, get_source, purge_expired, store_document

pytestmark = pytest.mark.integration

Handler = Callable[[httpx.Request], httpx.Response]


def pageviews(req: httpx.Request) -> httpx.Response:
    if "/per-article/" in req.url.path:
        items = [{"timestamp": f"202611{d:02d}00", "views": 100 * d} for d in (3, 1, 2)]
        return httpx.Response(200, json={"items": items})
    if "/top/" in req.url.path:
        arts = [
            {"article": "Main_Page", "views": 9_000_000, "rank": 1},
            {"article": "Special:Search", "views": 800_000, "rank": 2},
            {"article": "Student_loan", "views": 50_000, "rank": 3},
        ]
        return httpx.Response(200, json={"items": [{"articles": arts}]})
    return httpx.Response(404)


def feed(_req: httpx.Request) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=RSS)


SRC = "/api/v1/research-sources"
JAN = (date(2026, 1, 1), date(2026, 1, 2))


def fetcher(handler: Handler) -> ResearchFetcher:
    dns = resolver({"wikimedia.org": ["185.15.59.224"], "news.example.org": ["93.184.215.14"]})
    return ResearchFetcher(transport=httpx.MockTransport(handler), resolver=dns, contact="")


@pytest.fixture
def db(env: Env) -> Iterator[Session]:
    engine = create_engine(env.db_url)
    with Session(engine, expire_on_commit=False) as s:
        yield s
    engine.dispose()


def test_registry_is_seeded_with_safe_defaults(db: Session) -> None:
    rows = {r.code: r for r in db.scalars(select(ResearchSource))}
    assert set(rows) == {"WIKIPEDIA_PAGEVIEWS", "TRENDS_API_ALPHA", "OWNER_NOTES", "OWN_ANALYTICS"}
    wiki = rows["WIKIPEDIA_PAGEVIEWS"]
    assert (wiki.enabled, wiki.approval_status, wiki.allowed_hosts) == (True, "APPROVED", ["wikimedia.org"])
    assert wiki.terms_verified_at is None  # the owner confirms the terms
    t = rows["TRENDS_API_ALPHA"]
    assert (t.enabled, t.approval_status) == (False, "REQUIRES_OWNER_APPROVAL")


def test_wikipedia_pageviews_and_top_are_stored_as_evidence(db: Session) -> None:
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        return pageviews(req)

    with fetcher(handler) as f:
        api = wikipedia.WikipediaPageviews(db, f)
        series = api.per_article("en.wikipedia", "Student loan", date(2026, 11, 1), date(2026, 11, 3))
        top = api.top("en.wikipedia", date(2026, 11, 1))
        again = api.per_article("en.wikipedia", "Student loan", date(2026, 11, 1), date(2026, 11, 3))
    db.commit()
    assert seen[0] == (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
        "Student_loan/daily/2026110100/2026110300"
    )
    assert seen[1].endswith("/top/en.wikipedia/all-access/2026/11/01")
    assert series.points == [(date(2026, 11, d), 100 * d) for d in (1, 2, 3)]
    assert top.articles == [("Student_loan", 50_000, 3)]  # Main_Page and Special: pages dropped
    assert again.document_id == series.document_id  # identical content → one document, expiry refreshed
    doc = db.get_one(SourceDocument, series.document_id)
    assert doc.language == "en" and "2026-11-02: 200" in doc.content_text
    assert doc.expires_at - doc.fetched_at == timedelta(days=90)
    with pytest.raises(ValueError, match="project"), fetcher(handler) as f:
        wikipedia.WikipediaPageviews(db, f).per_article("evil.com", "X", *JAN)
    with pytest.raises(ValueError, match="400 days"), fetcher(handler) as f:
        wikipedia.WikipediaPageviews(db, f).per_article(
            "en.wikipedia", "X", date(2024, 1, 1), date(2026, 1, 2)
        )


def test_emergency_stop_and_switched_off_sources_fetch_nothing(db: Session) -> None:
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        return pageviews(req)

    db.get_one(SystemSettings, 1).emergency_stop = True
    db.commit()
    with pytest.raises(SourceUnavailableError) as stopped, fetcher(handler) as f:
        wikipedia.WikipediaPageviews(db, f).per_article(
            "en.wikipedia", "X", date(2026, 1, 1), date(2026, 1, 2)
        )
    assert stopped.value.code == "STOPPED"
    db.get_one(SystemSettings, 1).emergency_stop = False
    get_source(db, "WIKIPEDIA_PAGEVIEWS").enabled = False
    db.commit()
    with pytest.raises(SourceUnavailableError) as off, fetcher(handler) as f:
        wikipedia.WikipediaPageviews(db, f).per_article(
            "en.wikipedia", "X", date(2026, 1, 1), date(2026, 1, 2)
        )
    assert off.value.code == "SOURCE_OFF" and calls == []
    with pytest.raises(SourceUnavailableError) as alpha:
        trends.interest_over_time(db, "budget")
    assert alpha.value.code == "NOT_APPROVED"


def test_rss_items_become_documents_and_retention_purges_them(db: Session) -> None:
    src = ResearchSource(
        code="RSS:news",
        kind="RSS",
        base_url="https://news.example.org/feed.xml",
        allowed_hosts=["news.example.org"],
        approval_status="APPROVED",
        enabled=True,
    )
    db.add(src)
    db.commit()
    with fetcher(feed) as f:
        result = rss.read_feed(db, f, src)
    db.commit()
    assert result.title == "Money News" and len(result.items) == 2
    docs = db.scalars(select(SourceDocument).where(SourceDocument.source_id == src.id)).all()
    assert {d.url for d in docs} >= {"https://example.org/a"}
    assert any(d.url.startswith("https://news.example.org/feed.xml#item-") for d in docs)
    assert all("x()" not in d.content_text for d in docs)
    old = store_document(db, src, url="https://news.example.org/old", title="Old", text="old news",
                         now=datetime.now(UTC) - timedelta(days=91))  # fmt: skip
    db.commit()
    assert purge_expired(db) == 1
    db.commit()
    assert db.get(SourceDocument, old.id) is None
    assert (
        db.scalar(select(func.count()).select_from(SourceDocument).where(SourceDocument.source_id == src.id))
        == 2
    )


# ------------------------------------------------------------------------------------------- API
@pytest.fixture
def api(env: Env) -> Iterator[tuple[TestClient, dict[str, str], dict[str, Handler]]]:
    app = create_app(env.app_settings)
    route: dict[str, Handler] = {"handler": pageviews}
    app.state.research_fetcher_factory = lambda: fetcher(lambda req: route["handler"](req))
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        yield client, login(client), route


def test_api_lists_adds_approves_and_test_fetches(
    api: tuple[TestClient, dict[str, str], dict[str, Handler]], env: Env
) -> None:
    client, h, route = api
    sources = {s["code"]: s for s in client.get(SRC).json()}
    wiki = sources["WIKIPEDIA_PAGEVIEWS"]
    assert wiki["fetchable"] and not sources["OWNER_NOTES"]["fetchable"]

    r = client.post(f"{SRC}/{wiki['id']}/test", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["documents_stored"] == 1 and "Main Page" in r.json()["samples"][0]["title"]
    assert client.get(f"{SRC}/{wiki['id']}/documents").json()[0]["excerpt"]

    for bad, code in (
        ("https://www.youtube.com/feeds/videos.xml?channel_id=x", "INVALID_URL"),
        ("http://news.example.org/feed.xml", "INVALID_URL"),
        ("https://10.0.0.8/feed.xml", "INVALID_URL"),
    ):
        r = client.post(SRC, json={"kind": "RSS", "slug": "bad", "url": bad}, headers=h)
        assert (r.status_code, r.json()["code"]) == (422, code), bad
    body = {"kind": "RSS", "slug": "money-news", "url": "https://news.example.org/feed.xml"}
    r = client.post(SRC, json=body, headers=h)
    assert r.status_code == 201, r.text
    feed_src = r.json()
    assert (feed_src["code"], feed_src["enabled"], feed_src["approval_status"]) == (
        "RSS:money-news",
        False,
        "REQUIRES_OWNER_APPROVAL",
    )
    assert feed_src["allowed_hosts"] == ["news.example.org"]
    assert client.post(SRC, json=body, headers=h).json()["code"] == "DUPLICATE_SOURCE"

    route["handler"] = feed
    r = client.post(f"{SRC}/{feed_src['id']}/test", headers=h)
    assert (r.status_code, r.json()["code"]) == (409, "NOT_APPROVED")

    # Switching on a source that needs approval asks for the password again.
    r = client.patch(f"{SRC}/{feed_src['id']}", json={"enabled": True}, headers=h)
    assert r.status_code == 403 and r.json()["code"] == "REAUTH_REQUIRED"
    assert client.post("/api/v1/auth/reauth", json={"password": OWNER_PASSWORD}, headers=h).status_code == 204
    r = client.patch(
        f"{SRC}/{feed_src['id']}",
        json={"enabled": True, "terms_verified": True},
        headers=h,
    )
    assert (
        r.status_code == 200 and r.json()["approval_status"] == "APPROVED" and r.json()["terms_verified_at"]
    )
    r = client.post(f"{SRC}/{feed_src['id']}/test", headers=h)
    assert r.status_code == 200 and r.json()["documents_stored"] == 2
    actions = {a for (a,) in env.sql("SELECT action FROM audit_log WHERE entity_type = 'research_source'")}
    assert {"research_source.added", "research_source.enabled", "research_source.test_fetch"} <= actions

    route["handler"] = lambda _r: httpx.Response(
        200, headers={"content-type": "text/html"}, content=b"<p>x</p>"
    )
    r = client.post(f"{SRC}/{feed_src['id']}/test", headers=h)
    assert (r.status_code, r.json()["code"]) == (502, "FETCH_FAILED")
    route["handler"] = lambda _r: httpx.Response(302, headers={"location": "https://www.youtube.com/"})
    r = client.post(f"{SRC}/{feed_src['id']}/test", headers=h)
    assert (r.status_code, r.json()["code"]) == (422, "FETCH_BLOCKED")

    r = client.patch(f"{SRC}/{feed_src['id']}", json={"enabled": False}, headers=h)
    assert r.json()["enabled"] is False
    trends_id = sources["TRENDS_API_ALPHA"]["id"]
    assert client.post(f"{SRC}/{trends_id}/test", headers=h).json()["code"] == "NOT_APPROVED"
    owner_id = sources["OWNER_NOTES"]["id"]
    assert client.post(f"{SRC}/{owner_id}/test", headers=h).json()["code"] == "NOT_FETCHABLE"


def test_blocked_source_cannot_be_enabled(
    api: tuple[TestClient, dict[str, str], dict[str, Handler]], env: Env
) -> None:
    client, h, _route = api
    env.sql("UPDATE research_sources SET approval_status = 'BLOCKED' WHERE code = 'TRENDS_API_ALPHA'")
    t = next(s for s in client.get(SRC).json() if s["code"] == "TRENDS_API_ALPHA")
    r = client.patch(f"{SRC}/{t['id']}", json={"enabled": True}, headers=h)
    assert (r.status_code, r.json()["code"]) == (409, "SOURCE_BLOCKED")


def test_viewer_cannot_change_sources(env: Env, add_user) -> None:  # type: ignore[no-untyped-def]
    add_user("viewer@example.com", "VIEWER")
    with env.client() as client:
        h = login(client, "viewer@example.com")
        assert client.get(SRC).status_code in (200, 403)
        body = {"kind": "RSS", "slug": "x-feed", "url": "https://news.example.org/f.xml"}
        assert client.post(SRC, json=body, headers=h).status_code == 403
