"""Live pipeline progress (owner request 2026-11-18, ADR-0031): job_progress, /pipeline, Write again."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from tests.integration.conftest import Env, login
from tubeforge import progress
from tubeforge.db.ids import uuid7
from tubeforge.db.models import Channel, JobProgress, VideoProject

pytestmark = pytest.mark.integration


@pytest.fixture
def eng(env: Env) -> Iterator[Engine]:
    engine_ = create_engine(env.db_url)
    yield engine_
    engine_.dispose()


@pytest.fixture
def api(env: Env) -> Iterator[tuple[TestClient, dict[str, str]]]:
    with env.client() as client:
        yield client, login(client)


def idem(h: dict[str, str]) -> dict[str, str]:
    return {**h, "Idempotency-Key": str(uuid.uuid4())}


def started_project(eng: Engine, client: TestClient, h: dict[str, str]) -> str:
    with Session(eng) as s:
        ch = Channel(id=uuid7(), name="Open Node Test", state="ACTIVE", content_language="en")
        s.add(ch)
        s.commit()
        channel_id = str(ch.id)
    pid = client.post(
        "/api/v1/projects",
        json={"channel_id": channel_id, "working_title": "Local code completion explained"},
        headers=idem(h),
    ).json()["id"]
    assert client.post(f"/api/v1/projects/{pid}/commands/start", headers=idem(h)).status_code == 202
    return str(pid)


def row_for(eng: Engine, pid: str) -> JobProgress:
    with Session(eng) as s:
        row = s.scalar(
            select(JobProgress)
            .where(JobProgress.project_id == uuid.UUID(pid))
            .order_by(JobProgress.queued_at.desc())
            .limit(1)
        )
        assert row is not None
        return row


def item(client: TestClient, pid: str) -> dict[str, Any]:
    body = client.get("/api/v1/pipeline").json()
    return next(p for p in body["projects"] if p["id"] == pid)


def test_queued_running_done_and_next_station(
    api: tuple[TestClient, dict[str, str]], eng: Engine, env: Env
) -> None:
    client, h = api
    pid = started_project(eng, client, h)

    # Queued in the same transaction as the job: the line shows it waiting for a worker.
    queued = item(client, pid)
    assert (queued["station"], queued["activity"]) == ("research", "QUEUED")
    assert queued["progress"]["status"] == "QUEUED" and queued["progress"]["pct"] == 0
    assert queued["next"] == {
        "key": "research_review",
        "label": "Check the research",
        "who": "OWNER",
        "phase": 7,
        "ready": True,
        "count": 0,
        "board": None,
    }
    assert [s["status"] for s in queued["steps"][:3]] == ["current", "next", "later"]
    stations = client.get("/api/v1/pipeline").json()["stations"]
    assert stations[0]["count"] == 1
    assert {k: v for k, v in stations[4].items() if k != "board"} == {
        "key": "storyboard",
        "label": "Storyboard",
        "who": "TUBEFORGE",
        "phase": 8,
        "ready": False,
        "count": 0,
    }
    research = stations[0]["board"]
    assert (research["received_from"], research["forwards_to"]) == ("Approved idea", "Check the research")
    assert [(x["id"], x["activity"]) for x in research["inbox"]] == [(pid, "QUEUED")]
    assert (research["in_progress"], research["complete"], research["forwarded"]) == ([], 0, [])
    assert client.get(f"/api/v1/projects/{pid}").json()["progress"]["status"] == "QUEUED"

    # The worker reports progress in its own transactions: visible while the job runs.
    with progress.track(eng, "content.research", {"project_id": pid}) as tracker:
        assert tracker is not None
        progress.report(40, "Reading articles (3 of 6)")
        progress.report(20, "Never goes backwards")
        running = item(client, pid)
        assert running["activity"] == "WORKING"
        working = client.get("/api/v1/pipeline").json()["stations"][0]["board"]
        assert [(x["id"], x["pct"]) for x in working["in_progress"]] == [(pid, 40)]
        assert (running["progress"]["pct"], running["progress"]["stage"]) == (40, "Never goes backwards")
        assert client.get("/api/v1/pipeline").json()["refresh_s"] == 3
    done = row_for(eng, pid)
    assert (done.status, done.pct, done.stage) == ("DONE", 100, "Done") and done.finished_at is not None


def test_failure_waiting_and_retry(api: tuple[TestClient, dict[str, str]], eng: Engine, env: Env) -> None:
    client, h = api
    pid = started_project(eng, client, h)
    with progress.track(eng, "content.research", {"project_id": pid}):
        progress.finish("FAILED", "Only 1 Wikipedia article was found.")
    stopped = item(client, pid)
    assert stopped["activity"] == "STOPPED"
    assert client.get("/api/v1/pipeline").json()["stations"][0]["board"]["attention"] == 1
    assert stopped["progress"]["message"] == "Only 1 Wikipedia article was found."

    # A worker that dies mid-job leaves RUNNING; the next run marks it FAILED and starts fresh.
    assert client.post(f"/api/v1/projects/{pid}/commands/retry-research", headers=idem(h)).status_code == 202
    assert item(client, pid)["activity"] == "QUEUED"
    with pytest.raises(RuntimeError), progress.track(eng, "content.research", {"project_id": pid}):
        raise RuntimeError("provider exploded")
    assert row_for(eng, pid).message == "provider exploded"
    with progress.track(eng, "content.research", {"project_id": pid}):
        progress.finish("WAITING", "A free-tier limit was reached; it continues later.")
    assert item(client, pid)["activity"] == "WAITING"
    assert progress.current() is None
    progress.report(50, "No tracker: nothing happens")


def test_stalled_and_slow_queue_hints(api: tuple[TestClient, dict[str, str]], eng: Engine, env: Env) -> None:
    client, h = api
    pid = started_project(eng, client, h)
    old = datetime.now(UTC) - timedelta(minutes=30)
    env.sql("UPDATE job_progress SET queued_at = :t WHERE project_id = :p", t=old, p=pid)
    assert "TubeForge is running" in item(client, pid)["progress"]["hint"]
    # The updated_at trigger sets now() on UPDATE: a stalled row is inserted directly.
    env.sql("DELETE FROM job_progress WHERE project_id = :p", p=pid)
    env.sql(
        "INSERT INTO job_progress (id, kind, entity_type, entity_id, project_id, status, pct, stage,"
        " queued_at, started_at, updated_at) VALUES (:id, 'content.research', 'video_project', :p, :p,"
        " 'RUNNING', 30, 'Reading articles', :t, :t, :t)",
        id=str(uuid7()),
        p=pid,
        t=old,
    )
    stalled = item(client, pid)
    assert stalled["activity"] == "STALLED" and "No news for 30 minutes" in stalled["progress"]["hint"]
    # No job at all at a TubeForge station: the line says so instead of "in work".
    env.sql("DELETE FROM job_progress WHERE project_id = :p", p=pid)
    lost = item(client, pid)
    assert (lost["activity"], lost["progress"]) == ("STALLED", None)


def test_eta_from_earlier_runs_and_owner_station(
    api: tuple[TestClient, dict[str, str]], eng: Engine, env: Env
) -> None:
    client, h = api
    pid = started_project(eng, client, h)
    t0 = datetime.now(UTC) - timedelta(hours=1)
    env.sql(
        "INSERT INTO job_progress (id, kind, entity_type, entity_id, status, pct, stage, queued_at,"
        " started_at, finished_at) VALUES (:id, 'content.research', 'video_project', :e, 'DONE', 100,"
        " 'Done', :t, :t, :f)",
        id=str(uuid7()),
        e=str(uuid7()),
        t=t0,
        f=t0 + timedelta(seconds=120),
    )
    with progress.track(eng, "content.research", {"project_id": pid}):
        progress.report(10, "Searching Wikipedia")
        eta = item(client, pid)["progress"]["eta_s"]
        assert eta is not None and 60 <= eta <= 120

    with Session(eng) as s:
        project = s.get_one(VideoProject, uuid.UUID(pid))
        project.state = "RESEARCH_REVIEW"
        s.commit()
    review = item(client, pid)
    assert (review["station"], review["activity"], review["progress"]) == (
        "research_review",
        "YOUR_TURN",
        None,
    )
    assert review["next"]["key"] == "script" and review["steps"][0]["status"] == "done"
    board = {st["key"]: st["board"] for st in client.get("/api/v1/pipeline").json()["stations"]}
    assert board["research"]["complete"] == 1
    assert [x["title"] for x in board["research"]["forwarded"]] == ["Local code completion explained"]
    assert [x["id"] for x in board["research_review"]["inbox"]] == [pid]
    assert board["research_review"]["received_from"] == "Research"


def test_write_again_and_channel_jobs(api: tuple[TestClient, dict[str, str]], eng: Engine, env: Env) -> None:
    client, h = api
    pid = started_project(eng, client, h)
    cmd = f"/api/v1/projects/{pid}/commands"
    early = client.post(f"{cmd}/retry-script", headers=idem(h))
    assert early.status_code == 409 and "script writing" in early.json()["detail"]
    with Session(eng) as s:
        s.get_one(VideoProject, uuid.UUID(pid)).state = "SCRIPTING"
        s.commit()
    assert "retry-script" in client.get(f"/api/v1/projects/{pid}").json()["allowed_commands"]
    again = client.post(f"{cmd}/retry-script", json={"note": "Shorter hook, please."}, headers=idem(h))
    assert again.status_code == 202 and again.json()["project"]["state"] == "SCRIPTING"
    (args,) = env.sql(
        "SELECT args FROM procrastinate_jobs WHERE task_name LIKE '%content.script' ORDER BY id DESC LIMIT 1"
    )[0]
    assert args == {"project_id": pid, "instruction": "Shorter hook, please."}
    assert item(client, pid)["progress"]["kind"] == "content.script"

    channel_id = item(client, pid)["channel_id"]
    gen = client.post(f"/api/v1/channels/{channel_id}/ideas/generate", json={"count": 5}, headers=idem(h))
    assert gen.status_code == 202
    jobs = client.get(f"/api/v1/pipeline?channel_id={channel_id}").json()["jobs"]
    assert [(j["label"], j["status"], j["link"]) for j in jobs] == [
        ("New ideas", "QUEUED", f"/channels/{channel_id}/ideas")
    ]


def test_finished_progress_is_purged_after_30_days(eng: Engine, env: Env) -> None:
    old, recent = datetime.now(UTC) - timedelta(days=31), datetime.now(UTC) - timedelta(days=1)
    for finished in (old, recent, None):
        env.sql(
            "INSERT INTO job_progress (id, kind, entity_type, entity_id, status, pct, stage, finished_at)"
            " VALUES (:id, 'content.ideas', 'channel', :e, 'DONE', 100, 'Done', :f)",
            id=str(uuid7()),
            e=str(uuid7()),
            f=finished,
        )
    with Session(eng) as s:
        assert progress.purge_finished(s) == 1
        s.commit()
    assert env.sql("SELECT count(*) FROM job_progress")[0][0] == 2


def test_channel_cards_and_the_page_for_one_channel(
    api: tuple[TestClient, dict[str, str]], eng: Engine, env: Env
) -> None:
    """Owner request 2026-11-27: a card per channel on top; the rest of the page shows the picked channel."""
    client, h = api
    first = started_project(eng, client, h)  # channel "Open Node Test", research queued
    second = started_project(eng, client, h)
    with Session(eng) as s:
        project = s.get_one(VideoProject, uuid.UUID(second))
        project.state = "RESEARCH_REVIEW"
        other = s.get_one(Channel, project.channel_id)
        other.name = "Purfits Wellness Test"
        empty = Channel(id=uuid7(), name="Brand New Channel", state="ONBOARDING", content_language="en")
        s.add(empty)
        s.commit()
        a, b = str(s.get_one(VideoProject, uuid.UUID(first)).channel_id), str(other.id)

    everything = client.get("/api/v1/pipeline").json()
    cards = {c["name"]: c for c in everything["channels"]}
    assert list(cards) == ["Brand New Channel", "Open Node Test", "Purfits Wellness Test"]
    assert (cards["Open Node Test"]["videos"], cards["Open Node Test"]["queued"]) == (1, 1)
    assert (cards["Purfits Wellness Test"]["videos"], cards["Purfits Wellness Test"]["your_turn"]) == (1, 1)
    assert (cards["Brand New Channel"]["state"], cards["Brand New Channel"]["videos"]) == ("ONBOARDING", 0)
    assert len(everything["projects"]) == 2

    one = client.get(f"/api/v1/pipeline?channel_id={b}").json()
    assert one["channel_id"] == b and [p["id"] for p in one["projects"]] == [second]
    board = {st["key"]: st for st in one["stations"]}
    assert board["research"]["count"] == 0 and board["research"]["board"]["inbox"] == []
    assert [x["id"] for x in board["research_review"]["board"]["inbox"]] == [second]
    assert len(one["channels"]) == 3  # the cards always cover every channel
    assert [p["id"] for p in client.get(f"/api/v1/pipeline?channel_id={a}").json()["projects"]] == [first]
