"""Blueprint edit/propose/approve → channel, trends and keywords APIs (Phase 6 step D)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tests.integration.conftest import Env, login
from tests.unit import discovery_fixtures as fx
from tubeforge.db.ids import uuid7
from tubeforge.db.models import Channel, ChannelStrategy, NicheCandidate, NicheReport, TrendItem
from tubeforge.research import blueprint as bp

pytestmark = pytest.mark.integration


@pytest.fixture
def db(env: Env) -> Iterator[Session]:
    engine = create_engine(env.db_url)
    with Session(engine, expire_on_commit=False) as s:
        yield s
    engine.dispose()


@pytest.fixture
def api(env: Env) -> Iterator[tuple[TestClient, dict[str, str]]]:
    with env.client() as client:
        yield client, login(client)


def _idem(h: dict[str, str]) -> dict[str, str]:
    return {**h, "Idempotency-Key": str(uuid.uuid4())}


def _draft(db: Session, env: Env) -> tuple[NicheCandidate, ChannelStrategy, ChannelStrategy]:
    rep = NicheReport(id=uuid7(), requested_by=env.owner.id, params={"languages": ["en"]}, status="DONE")
    db.add(rep)
    db.flush()
    cand = NicheCandidate(
        id=uuid7(), report_id=rep.id, name="Student budgets", summary="s", language="en", criteria=[],
        opportunity_score=Decimal("70"), inauthentic_risk="LOW", production_difficulty="LOW",
        status="SHORTLISTED",
    )  # fmt: skip
    db.add(cand)
    db.flush()
    blueprint = bp.compose(
        {"candidate_id": str(cand.id), "name": cand.name, "language": "en"},
        {**fx.strategy(), "ideas": fx.ideas()[:50]},
        fx.branding(),
    )
    main = ChannelStrategy(
        id=uuid7(), niche_candidate_id=cand.id, version=1, status="DRAFT", blueprint=blueprint
    )
    other = ChannelStrategy(
        id=uuid7(), niche_candidate_id=cand.id, version=2, status="DRAFT", blueprint=blueprint
    )
    db.add_all([main, other])
    db.commit()
    return cand, main, other


def test_blueprint_edit_propose_approve_creates_the_channel(
    api: tuple[TestClient, dict[str, str]], db: Session, env: Env
) -> None:
    client, h = api
    cand, main, other = _draft(db, env)
    url = f"/api/v1/strategies/{main.id}"
    got = client.get(url)
    etag = got.headers["ETag"].strip('"')
    assert got.json()["problems"] == [] and got.json()["etag"] == etag
    blueprint: dict[str, Any] = got.json()["blueprint"]

    assert client.patch(url, json={"blueprint": blueprint}, headers=h).status_code == 428
    assert (
        client.patch(url, json={"blueprint": blueprint}, headers={**h, "If-Match": '"stale"'}).status_code
        == 412
    )
    broken = {**blueprint, "ideas": blueprint["ideas"][:3]}
    r = client.patch(url, json={"blueprint": broken}, headers={**h, "If-Match": etag})
    assert (r.status_code, r.json()["code"]) == (422, "BLUEPRINT_INVALID")
    # a rule problem may be saved in a draft, but blocks propose
    dup = {**blueprint, "ideas": [*blueprint["ideas"][:49], {**blueprint["ideas"][0]}],
           "footer": "edited",
           "niche": {"candidate_id": None, "name": "hacked", "language": "de"}}  # fmt: skip
    r = client.patch(url, json={"blueprint": dup}, headers={**h, "If-Match": etag})
    assert r.status_code == 200 and any("near-duplicates" in p for p in r.json()["problems"])
    assert r.json()["blueprint"]["niche"]["name"] == "Student budgets"  # niche and footer cannot be edited
    assert r.json()["blueprint"]["footer"].startswith("Estimates based on cited sources")
    r2 = client.post(f"{url}/commands/propose", headers=h)
    assert (r2.status_code, r2.json()["code"]) == (409, "BLUEPRINT_HAS_PROBLEMS")
    fixed = {**blueprint, "description": "Real student budgets, explained plainly with my own spreadsheets."}
    r = client.patch(url, json={"blueprint": fixed}, headers={**h, "If-Match": r.json()["etag"]})
    assert r.status_code == 200 and r.json()["problems"] == []

    assert client.post(f"{url}/commands/approve", json={"channel_name": "x"}, headers=h).json()["code"] == (
        "INVALID_TRANSITION"
    )
    assert client.post(f"{url}/commands/propose", headers=h).json()["status"] == "PROPOSED"
    assert client.patch(url, json={"blueprint": fixed}, headers={**h, "If-Match": "x"}).status_code in (
        409,
        412,
    )
    assert client.post(f"{url}/commands/approve", headers=h).json()["code"] == "CHANNEL_NAME_REQUIRED"
    r = client.post(f"{url}/commands/approve", json={"channel_name": "Budget Lab 1"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "APPROVED" and r.json()["approved_at"]
    db.expire_all()
    channel = db.get_one(Channel, uuid.UUID(r.json()["channel_id"]))
    c = channel
    assert (c.name, c.state, c.is_test_channel, c.is_monetised, c.content_language) == (
        "Budget Lab 1", "APPROVED", True, False, "en",
    )  # fmt: skip
    assert db.get_one(NicheCandidate, cand.id).status == "CONVERTED"
    assert db.get_one(ChannelStrategy, other.id).status == "SUPERSEDED"
    listed = client.get("/api/v1/channels").json()["items"]
    assert [c["name"] for c in listed] == ["Budget Lab 1"]

    nv = client.post(f"{url}/commands/new-version", headers=h).json()
    assert (nv["status"], nv["version"], nv["channel_id"]) == ("DRAFT", 2, r.json()["channel_id"])
    assert (
        client.post(f"/api/v1/strategies/{nv['id']}/commands/reject", headers=h).json()["status"]
        == "REJECTED"
    )
    actions = {a for (a,) in env.sql("SELECT action FROM audit_log")}
    assert {
        "blueprint.edited",
        "blueprint.propose",
        "blueprint.approve",
        "channel.created",
        "blueprint.new_version",
    } <= actions


def test_trends_list_dismiss_and_scan(api: tuple[TestClient, dict[str, str]], db: Session, env: Env) -> None:
    client, h = api
    ch = Channel(id=uuid7(), name="Budget Lab", state="ACTIVE", content_language="en")
    db.add(ch)
    db.flush()
    now = datetime.now(UTC)
    live = TrendItem(id=uuid7(), channel_id=ch.id, topic="Rent rises", summary="s", source_document_ids=[],
                     signal_strength=Decimal("2.5"), confidence="MEDIUM", detected_at=now,
                     expires_at=now + timedelta(days=5))  # fmt: skip
    old = TrendItem(id=uuid7(), channel_id=ch.id, topic="Old news", summary="s", source_document_ids=[],
                    signal_strength=Decimal("4"), confidence="LOW", detected_at=now - timedelta(days=9),
                    expires_at=now - timedelta(days=1))  # fmt: skip
    db.add_all([live, old])
    db.commit()
    assert [t["topic"] for t in client.get(f"/api/v1/trends?channel_id={ch.id}").json()] == ["Rent rises"]
    every = {
        t["topic"]: t["status"]
        for t in client.get(f"/api/v1/trends?channel_id={ch.id}&include_inactive=true").json()
    }
    assert every == {"Rent rises": "ACTIVE", "Old news": "EXPIRED"}
    r = client.post(f"/api/v1/trends/{live.id}/commands/to-idea", headers=h)
    assert (r.status_code, r.json()["code"]) == (409, "NOT_AVAILABLE_YET")
    assert (
        client.post(f"/api/v1/trends/{live.id}/commands/dismiss", headers=h).json()["status"] == "DISMISSED"
    )
    assert client.post(f"/api/v1/trends/{live.id}/commands/dismiss", headers=h).json()["code"] == "NOT_ACTIVE"
    r = client.post("/api/v1/trends/scan", json={"channel_id": str(ch.id)}, headers=_idem(h))
    assert r.status_code == 202
    assert env.sql("SELECT count(*) FROM procrastinate_jobs WHERE task_name LIKE '%research.trend_scan'") == [
        (1,)
    ]


def test_keywords(api: tuple[TestClient, dict[str, str]], db: Session, env: Env) -> None:
    client, h = api
    ch = Channel(id=uuid7(), name="Budget Lab", state="ACTIVE", content_language="en")
    db.add(ch)
    db.commit()
    url = f"/api/v1/channels/{ch.id}/keywords"
    r = client.post(url, json={"phrase": "student  budget  template"}, headers=h)
    assert r.status_code == 201 and r.json()["phrase"] == "student budget template"
    assert (
        client.post(url, json={"phrase": "student budget template"}, headers=h).json()["code"]
        == "DUPLICATE_KEYWORD"
    )
    assert (
        client.post(url, json={"phrase": "guaranteed savings"}, headers=h).json()["code"]
        == "FORBIDDEN_PHRASE"
    )
    assert client.post(url, json={}, headers=h).status_code == 422
    r = client.post(url, json={"seeds": ["student budget"]}, headers=_idem(h))
    assert r.status_code == 202 and r.json()["status"] == "QUEUED"
    listed = client.get(url).json()
    assert [k["phrase"] for k in listed] == ["student budget template"] and listed[0][
        "notes"
    ] == "Added by the owner"
    assert client.delete(f"{url}/{listed[0]['id']}", headers=h).status_code == 204
    assert client.get(url).json() == []
