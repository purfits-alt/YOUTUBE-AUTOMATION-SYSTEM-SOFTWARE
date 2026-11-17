"""Phase 7 step C: ideas, calendar, replicate, projects, research, claims and script APIs."""

# ruff: noqa: E501  (table-style requests)
from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tests.integration.conftest import Env, login
from tests.unit import content_fixtures as fx
from tubeforge.audit import Actor
from tubeforge.content import scripts
from tubeforge.db.ids import uuid7
from tubeforge.db.models import (
    Channel,
    FactCheckClaim,
    ResearchBrief,
    Script,
    ScriptVersion,
    SourceDocument,
    VideoProject,
)
from tubeforge.orchestrator import engine
from tubeforge.orchestrator.machines import MACHINES
from tubeforge.research.sources import get_source

pytestmark = pytest.mark.integration
PROMISE = {
    "title_idea": "Where my 9,000 rupees went",
    "thumbnail_text_idea": "9,000 WASTED",
    "promise_statement": "Show where a student lost 9,000 rupees in a month and how to stop it.",
}


@pytest.fixture
def db(env: Env) -> Iterator[Session]:
    engine_ = create_engine(env.db_url)
    with Session(engine_, expire_on_commit=False) as s:
        yield s
    engine_.dispose()


@pytest.fixture
def api(env: Env) -> Iterator[tuple[TestClient, dict[str, str]]]:
    with env.client() as client:
        yield client, login(client)


def idem(h: dict[str, str]) -> dict[str, str]:
    return {**h, "Idempotency-Key": str(uuid.uuid4())}


def channel(db: Session) -> Channel:
    ch = Channel(id=uuid7(), name="Open Node Test", state="ACTIVE", content_language="en")
    db.add(ch)
    db.commit()
    return ch


def jobs(env: Env, name: str) -> int:
    rows = env.sql("SELECT count(*) FROM procrastinate_jobs WHERE task_name LIKE :n", n=f"%{name}")
    return int(str(rows[0][0]))


# ------------------------------------------------------------------------------------- ideas
def test_ideas_calendar_and_approval(api: tuple[TestClient, dict[str, str]], db: Session, env: Env) -> None:
    client, h = api
    ch = channel(db)
    base = f"/api/v1/channels/{ch.id}/ideas"
    first = client.post(
        base,
        json={"title": "How I budget as a student in 2026", "angle": "My own spending log"},
        headers=idem(h),
    )
    assert (
        first.status_code == 201
        and first.json()["source"] == "OWNER"
        and first.json()["similarity_max"] is None
    )
    dup = client.post(
        base,
        json={"title": "How I budget as a student in 2026", "angle": "Again", "packaging_promise": PROMISE},
        headers=idem(h),
    ).json()
    assert dup["duplicate"] is True and dup["similar_to_title"] == "How I budget as a student in 2026"
    bad = client.post(
        base, json={"title": "A guaranteed way to save", "angle": "Easy money"}, headers=idem(h)
    )
    assert (bad.status_code, bad.json()["code"]) == (422, "FORBIDDEN_PHRASE")

    page = client.get(f"{base}?q=budget&limit=1").json()
    assert len(page["items"]) == 1 and page["next_cursor"]
    assert len(client.get(f"{base}?cursor={page['next_cursor']}").json()["items"]) == 1

    # Edit with If-Match; a stale version is refused.
    url = f"/api/v1/ideas/{dup['id']}"
    edit = {
        "title": "My student budget, one year later",
        "angle": "A yearly update",
        "packaging_promise": PROMISE,
    }
    assert client.patch(url, json=edit, headers={**h, "If-Match": '"9"'}).json()["code"] == "VERSION_CONFLICT"
    edited = client.patch(url, json=edit, headers={**h, "If-Match": '"1"'}).json()
    assert edited["version"] == 2 and edited["title"] == "My student budget, one year later"

    # Generate queues A08.
    r = client.post(f"{base}/generate", json={"count": 5, "format": "SHORT"}, headers=idem(h))
    assert r.status_code == 202 and jobs(env, "content.ideas") == 1

    # Schedule → calendar → move.
    cmd = f"/api/v1/ideas/{first.json()['id']}/commands"
    assert client.post(f"{cmd}/shortlist", headers=idem(h)).json()["idea"]["state"] == "SHORTLISTED"
    day = date.today() + timedelta(days=3)
    assert client.post(f"{cmd}/schedule", json={}, headers=idem(h)).status_code == 400
    assert (
        client.post(f"{cmd}/schedule", json={"date": str(day)}, headers=idem(h)).json()["idea"]["state"]
        == "SCHEDULED"
    )
    cal = client.get(
        f"/api/v1/calendar?from={day - timedelta(days=1)}&to={day + timedelta(days=7)}&channel_id={ch.id}"
    ).json()
    assert [(i["title"], i["date"]) for i in cal["items"]] == [
        ("How I budget as a student in 2026", str(day))
    ]
    moved = client.patch(
        f"/api/v1/calendar/items/{first.json()['id']}", json={"date": str(day + timedelta(days=1))}, headers=h
    )
    assert moved.json()["date"] == str(day + timedelta(days=1))
    assert (
        len(
            client.get(
                f"/api/v1/calendar?from={day - timedelta(days=150)}&to={day + timedelta(days=200)}"
            ).json()["items"]
        )
        == 0
    )  # cut to 120 days
    assert client.get(f"/api/v1/calendar?from={day}&to={day - timedelta(days=1)}").json() == {"items": []}

    # Approving a scheduled idea creates the project and queues research.
    approved = client.post(f"{cmd}/approve", json={"target_duration_s": 600}, headers=idem(h))
    assert approved.status_code == 202, approved.text
    body = approved.json()
    assert body["idea"]["state"] == "IN_PRODUCTION" and body["project_id"] and len(body["job_ids"]) == 1
    project = client.get(f"/api/v1/projects/{body['project_id']}").json()
    assert (project["state"], project["target_duration_s"], project["format"]) == ("RESEARCHING", 600, "LONG")
    assert jobs(env, "content.research") == 1

    # The near-duplicate (similar to the first idea) needs a written reason.
    again = client.post(
        base, json={"title": "How I budget as a student in 2026", "angle": "Third try"}, headers=idem(h)
    ).json()
    dcmd = f"/api/v1/ideas/{again['id']}/commands"
    client.post(f"{dcmd}/shortlist", headers=idem(h))
    refused = client.post(f"{dcmd}/approve", json={}, headers=idem(h))
    assert refused.status_code == 409 and "Too similar" in refused.json()["detail"]
    assert client.get(f"/api/v1/ideas/{again['id']}").json()["state"] == "SHORTLISTED"  # nothing half-done
    ok = client.post(
        f"{dcmd}/approve",
        json={"override_reason": "A follow-up with new numbers from this year."},
        headers=idem(h),
    )
    assert ok.status_code == 202
    assert client.post(f"/api/v1/ideas/{again['id']}/commands/discard", headers=idem(h)).status_code == 409


# ---------------------------------------------------------------------------------- projects
def _brief(db: Session, project: VideoProject, contradicted: bool) -> ResearchBrief:
    source = get_source(db, "WIKIPEDIA_ARTICLES")
    doc = SourceDocument(id=uuid7(), source_id=source.id, url="https://en.wikipedia.org/wiki/Budget", title="Budget",
                         content_sha256="0" * 64, content_text="A budget is a financial plan.", language="en",
                         fetched_at=project.created_at, expires_at=project.created_at + timedelta(days=30))  # fmt: skip
    db.add(doc)
    claims = [
        {"id": "c1", "text": "A budget is a plan.", "source_document_ids": [str(doc.id)], "verdict": "SUPPORTED"},
        {"id": "c2", "text": "Most students budget.", "source_document_ids": [str(doc.id)], "verdict": "CONTRADICTED" if contradicted else "SUPPORTED"},
    ]  # fmt: skip
    brief = ResearchBrief(id=uuid7(), project_id=project.id, channel_id=project.channel_id, version=1, status="SUBMITTED",
                          content={"summary": "s", "claims": claims, "documents": [{"id": str(doc.id), "url": doc.url, "title": "Budget"}]})  # fmt: skip
    db.add(brief)
    db.flush()
    for c in claims:
        db.add(FactCheckClaim(id=uuid7(), project_id=project.id, channel_id=project.channel_id, subject_type="RESEARCH_BRIEF",
                              subject_id=brief.id, claim_text=f"{c['id']}: {c['text']}", verdict=c["verdict"],
                              source_document_ids=[doc.id], explanation="x"))  # fmt: skip
    engine.transition(db, MACHINES["video_project"], project.id, "research_done", actor=Actor("AGENT", "A09_RESEARCH"),
                      payload={"research_done": True, "fact_check_done": True})  # fmt: skip
    db.commit()
    return brief


def _draft(db: Session, project: VideoProject) -> ScriptVersion:
    script = Script(id=uuid7(), project_id=project.id, channel_id=project.channel_id)
    db.add(script)
    db.flush()
    body = fx.long_script()
    info = scripts.summary(body)
    version = ScriptVersion(id=uuid7(), script_id=script.id, version=1, author_type="AGENT", author_id="A11_SCRIPTWRITING",
                            body={**body, "_fact_check": "DONE"}, plain_text=info["plain_text"], word_count=info["word_count"],
                            est_duration_s=info["est_duration_s"], content_sha256=info["content_sha256"])  # fmt: skip
    db.add(version)
    engine.transition(db, MACHINES["video_project"], project.id, "script_done", actor=Actor("AGENT", "A11_SCRIPTWRITING"),
                      payload={"script_done": True, "fact_check_done": True})  # fmt: skip
    db.commit()
    return version


def test_project_from_research_to_locked_script(
    api: tuple[TestClient, dict[str, str]], db: Session, env: Env
) -> None:
    client, h = api
    ch = channel(db)
    created = client.post(
        "/api/v1/projects",
        json={
            "channel_id": str(ch.id),
            "working_title": "Where my student budget went",
            "packaging_promise": PROMISE,
        },
        headers=idem(h),
    )
    assert created.status_code == 201
    pid = created.json()["id"]
    assert created.json()["allowed_commands"] == ["start", "cancel"]
    cmd = f"/api/v1/projects/{pid}/commands"
    started = client.post(f"{cmd}/start", headers=idem(h))
    assert started.status_code == 202 and started.json()["project"]["state"] == "RESEARCHING"
    assert "retry-research" in started.json()["project"]["allowed_commands"]
    again = client.post(f"{cmd}/retry-research", json={"note": "Code Llama, VS Code"}, headers=idem(h))
    assert again.status_code == 202 and again.json()["project"]["state"] == "RESEARCHING"
    (args,) = env.sql(
        "SELECT args FROM procrastinate_jobs WHERE task_name LIKE '%content.research' ORDER BY id DESC LIMIT 1"
    )[0]
    assert args["extra_queries"] == ["Code Llama", "VS Code"]  # type: ignore[index]
    assert client.post(f"{cmd}/approve-cut", headers=idem(h)).json()["code"] == "NOT_AVAILABLE_YET"

    project = db.get_one(VideoProject, uuid.UUID(pid))
    brief = _brief(db, project, contradicted=True)
    view = client.get(f"/api/v1/projects/{pid}").json()
    assert view["state"] == "RESEARCH_REVIEW"
    assert [(c["code"], c["ok"]) for c in view["checks"]] == [("research_brief_valid", False)]
    assert client.get(f"/api/v1/projects/{pid}/research").json()[0]["version"] == 1
    assert client.get(f"/api/v1/projects/{pid}/research/1").json()["status"] == "SUBMITTED"
    refused = client.post(f"{cmd}/approve-research", headers=idem(h))
    assert refused.status_code == 409 and "contradicted" in refused.json()["detail"]

    # Override the contradicted claim with a reason.
    claims = client.get(f"/api/v1/projects/{pid}/claims?subject=RESEARCH_BRIEF").json()
    bad = next(c for c in claims if c["verdict"] == "CONTRADICTED")
    assert bad["sources"][0]["url"] == "https://en.wikipedia.org/wiki/Budget"
    assert (
        client.post(
            f"/api/v1/claims/{bad['id']}/override", json={"reason": "short"}, headers=idem(h)
        ).status_code
        == 400
    )
    over = client.post(
        f"/api/v1/claims/{bad['id']}/override",
        json={"reason": "I will say it as my own opinion instead."},
        headers=idem(h),
    )
    assert over.status_code == 200 and over.json()["owner_override_reason"]
    assert client.get(f"/api/v1/projects/{pid}").json()["checks"][0]["ok"] is True
    approved = client.post(f"{cmd}/approve-research", headers=idem(h))
    assert approved.status_code == 202 and approved.json()["project"]["state"] == "SCRIPTING"
    db.refresh(brief)
    assert brief.status == "APPROVED" and jobs(env, "content.script") == 1

    # Script review: versions, findings, owner edit, fact-check gate, value-add gate, approval.
    v1 = _draft(db, project)
    got = client.get(f"/api/v1/projects/{pid}/script/versions/1").json()
    assert got["findings"] == [] and got["fact_check"] == "DONE" and "_fact_check" not in got["body"]
    assert 10 <= got["hook_s"] <= 15
    edited = fx.long_script()
    edited["sections"][0]["text"] = (
        "A brand new opening for the first section. " + edited["sections"][0]["text"]
    )
    assert (
        client.post(
            f"/api/v1/projects/{pid}/script/versions",
            json={"body": edited, "based_on_version": 2},
            headers=idem(h),
        ).status_code
        == 412
    )
    invalid = client.post(
        f"/api/v1/projects/{pid}/script/versions",
        json={"body": {"hook": {}}, "based_on_version": 1},
        headers=idem(h),
    )
    assert (invalid.status_code, invalid.json()["code"]) == (422, "SCRIPT_INVALID")
    saved = client.post(
        f"/api/v1/projects/{pid}/script/versions",
        json={"body": edited, "based_on_version": 1},
        headers=idem(h),
    )
    assert saved.status_code == 201
    v2: dict[str, Any] = saved.json()
    assert (v2["version"], v2["author_type"], v2["fact_check"]) == (2, "OWNER", "PENDING")
    assert jobs(env, "content.fact_check") == 1
    listed = client.get(f"/api/v1/projects/{pid}/script/versions").json()
    assert [v["version"] for v in listed] == [2, 1]
    diff = client.get(f"/api/v1/projects/{pid}/script/diff?a=1&b=2").json()
    assert any(line.startswith("+A brand new opening") for line in diff["lines"])

    pending = client.post(f"{cmd}/approve-script", headers=idem(h))
    assert pending.json()["code"] == "FACT_CHECK_PENDING"
    row = db.get_one(ScriptVersion, uuid.UUID(v2["id"]))
    row.body = {**row.body, "_fact_check": "DONE"}
    db.commit()
    no_value = client.post(f"{cmd}/approve-script", headers=idem(h))
    assert no_value.status_code == 409 and "Add your own value" in no_value.json()["detail"]
    value = client.put(
        f"/api/v1/projects/{pid}/value-add",
        json={"own_experience": "I logged every purchase for thirty days in a notebook."},
        headers=h,
    ).json()
    assert value["score"] == "25.00" and value["filled_fields"] == ["own_experience"]
    assert all(c["ok"] for c in client.get(f"/api/v1/projects/{pid}").json()["checks"])
    done = client.post(f"{cmd}/approve-script", headers=idem(h))
    assert done.status_code == 200, done.text
    assert done.json()["project"]["state"] == "STORYBOARDING"
    assert done.json()["project"]["locked_script_version_id"] == v2["id"]
    db.refresh(row)
    db.refresh(v1)
    assert row.locked and not v1.locked
    events = [t["event"] for t in client.get(f"/api/v1/projects/{pid}/timeline-history").json()]
    assert events == ["start_research", "research_done", "approve_research", "script_done", "approve_script"]
    assert (
        client.post(
            f"/api/v1/projects/{pid}/script/regenerate",
            json={"instruction": "Shorter hook please"},
            headers=idem(h),
        ).status_code
        == 409
    )


def test_regenerate_pause_resume_cancel(
    api: tuple[TestClient, dict[str, str]], db: Session, env: Env
) -> None:
    client, h = api
    ch = channel(db)
    pid = client.post(
        "/api/v1/projects",
        json={"channel_id": str(ch.id), "working_title": "Five apps for tracking money", "format": "SHORT"},
        headers=idem(h),
    ).json()["id"]
    project = db.get_one(VideoProject, uuid.UUID(pid))
    assert project.target_duration_s == 45
    cmd = f"/api/v1/projects/{pid}/commands"
    client.post(f"{cmd}/start", headers=idem(h))
    _brief(db, project, contradicted=False)
    client.post(f"{cmd}/approve-research", headers=idem(h))
    _draft(db, project)
    r = client.post(
        f"/api/v1/projects/{pid}/script/regenerate",
        json={"instruction": "Make the hook a question", "section": 1},
        headers=idem(h),
    )
    assert r.status_code == 202
    db.refresh(project)
    assert project.state == "SCRIPTING"
    args = env.sql(
        "SELECT args FROM procrastinate_jobs WHERE task_name LIKE '%content.script' ORDER BY id DESC LIMIT 1"
    )[0][0]
    assert "Rewrite section 1" in str(args)
    assert client.post(f"{cmd}/pause", headers=idem(h)).json()["project"]["state"] == "PAUSED"
    resumed = client.post(f"{cmd}/resume", headers=idem(h))
    assert resumed.status_code == 202 and resumed.json()["project"]["state"] == "SCRIPTING"
    assert (
        client.post(f"{cmd}/cancel", json={"note": "Not this one"}, headers=idem(h)).json()["project"][
            "state"
        ]
        == "CANCELLED"
    )
    assert (
        client.post(
            "/api/v1/projects",
            json={"channel_id": str(ch.id), "working_title": "From an idea", "idea_id": str(uuid.uuid4())},
            headers=idem(h),
        ).json()["code"]
        == "USE_IDEA_APPROVE"
    )


def test_replicate_only_own_videos(api: tuple[TestClient, dict[str, str]], db: Session, env: Env) -> None:
    client, h = api
    ch = channel(db)
    own = VideoProject(id=uuid7(), channel_id=ch.id, format="LONG", state="PUBLISHED", working_title="My 30-day student budget",
                       target_duration_s=480, render_profile={}, youtube_video_id="abcDEF12345")  # fmt: skip
    test = VideoProject(id=uuid7(), channel_id=ch.id, format="LONG", state="PRIVATE_DONE", working_title="Test",
                        target_duration_s=5, render_profile={}, youtube_video_id="testVID0001", is_test=True)  # fmt: skip
    db.add_all([own, test])
    db.commit()
    overview = client.get(f"/api/v1/channels/{ch.id}/replicate").json()
    assert [w["youtube_video_id"] for w in overview["winners"]] == ["abcDEF12345"] and overview[
        "variations"
    ] == []
    url = f"/api/v1/channels/{ch.id}/ideas/replicate"
    assert (
        client.post(
            url, json={"youtube_video_id": "someoneElse1", "kind": "NEW_ANGLE"}, headers=idem(h)
        ).status_code
        == 404
    )
    assert (
        client.post(
            url, json={"youtube_video_id": "testVID0001", "kind": "NEW_ANGLE"}, headers=idem(h)
        ).status_code
        == 404
    )
    r = client.post(
        url, json={"youtube_video_id": "abcDEF12345", "kind": "PART_2", "note": "Year two"}, headers=idem(h)
    )
    assert r.status_code == 202
    args = env.sql("SELECT args FROM procrastinate_jobs WHERE task_name LIKE '%content.ideas'")[0][0]
    assert args["variation"]["title"] == "My 30-day student budget" and args["variation"]["kind"] == "PART_2"  # type: ignore[index]
    assert db.scalar(select(VideoProject.id).where(VideoProject.youtube_video_id == "abcDEF12345")) == own.id
