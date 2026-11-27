"""Phase 8 step B: Storyboard Studio and Visual Studio APIs (page 12, page 14)."""
# ruff: noqa: E501  (table-style requests)

from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tests.integration.conftest import Env, login
from tubeforge.db.ids import uuid7
from tubeforge.db.models import Channel, Scene, Storyboard, VideoProject

pytestmark = pytest.mark.integration


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


def project_with_storyboard(db: Session, state: str = "ASSET_GENERATION") -> tuple[VideoProject, list[Scene]]:
    ch = Channel(id=uuid7(), name="Calm Science", state="ACTIVE", content_language="en")
    db.add(ch)
    db.flush()
    project = VideoProject(
        id=uuid7(), channel_id=ch.id, working_title="What a late dinner does to sleep", format="LONG",
        state=state, target_duration_s=480, render_profile={"profile": "LONG_1080"},
    )  # fmt: skip
    db.add(project)
    db.flush()
    board = Storyboard(id=uuid7(), project_id=project.id, channel_id=ch.id, version=1, author_type="AGENT")
    db.add(board)
    db.flush()
    scenes = [
        Scene(
            id=uuid7(), storyboard_id=board.id, position=i, narration=f"Sentence {i} about sleep.",
            visual_instruction="Big title", on_screen_text=None, duration_s=Decimal("4.5"), style="kinetic_text",
            is_hook=i == 1, template_id="kinetic_title",
            template_params={"text": f"Scene {i}", "_why": "", "_stock_search_terms": ["night sky"]},
        )
        for i in (1, 2, 3)
    ]  # fmt: skip
    db.add_all(scenes)
    db.commit()
    return project, scenes


def jobs(env: Env, name: str) -> list[object]:
    return [
        r[0] for r in env.sql("SELECT args FROM procrastinate_jobs WHERE task_name LIKE :n", n=f"%{name}")
    ]


def test_storyboard_view_owner_edits_and_scene_visual(
    api: tuple[TestClient, dict[str, str]], db: Session, env: Env
) -> None:
    client, h = api
    project, scenes = project_with_storyboard(db)
    url = f"/api/v1/projects/{project.id}/storyboard"
    got = client.get(url, headers=h).json()
    assert got["version"] == 1 and got["editable"] and got["total_duration_s"] == 13.5
    assert [s["position"] for s in got["scenes"]] == [1, 2, 3] and got["scenes"][0]["is_hook"]
    first = got["scenes"][0]
    assert first["template_params"] == {"text": "Scene 1"}  # TubeForge's notes are not template fields
    assert first["stock_search_terms"] == ["night sky"] and first["template_label"] == "Big title"
    ids = {t["id"] for t in got["templates"]}
    assert len(ids) == 16 and next(t for t in got["templates"] if t["id"] == "ken_burns_photo")["needs_media"]

    # The owner changes what scene 2 shows → version 2; narration and pictures stay.
    edits = [
        {"id": s["id"], "visual_instruction": s["visual_instruction"], "on_screen_text": s["on_screen_text"],
         "style": s["style"]}
        for s in got["scenes"]
    ]  # fmt: skip
    edits[1] = {**edits[1], "visual_instruction": "A clock at 11 pm", "on_screen_text": "11 pm dinner"}
    saved = client.put(url, json={"based_on_version": 1, "scenes": edits}, headers=idem(h))
    assert saved.status_code == 200, saved.text
    two = saved.json()
    assert two["version"] == 2 and two["author_type"] == "OWNER"
    assert two["scenes"][1]["on_screen_text"] == "11 pm dinner"
    assert [s["narration"] for s in two["scenes"]] == [s["narration"] for s in got["scenes"]]
    stale = client.put(url, json={"based_on_version": 1, "scenes": edits}, headers=idem(h))
    assert stale.status_code == 412
    bad = [*edits[:2], {**edits[2], "on_screen_text": "Guaranteed to fix your sleep"}]
    new_ids = [s["id"] for s in two["scenes"]]
    for e, i in zip(bad, new_ids, strict=True):
        e["id"] = i
    refused = client.put(url, json={"based_on_version": 2, "scenes": bad}, headers=idem(h))
    assert refused.status_code == 422 and refused.json()["code"] == "SCENE_INVALID"

    # Another template for one scene is drawn by a heavy job; media templates and bad fields are refused.
    scene_url = f"/api/v1/projects/{project.id}/scenes/{new_ids[1]}/visual"
    ok = client.put(scene_url, json={"template_id": "number_counter",
                                     "params": {"value": "11 pm", "label": "dinner time"}}, headers=idem(h))  # fmt: skip
    assert ok.status_code == 202, ok.text
    assert jobs(env, "media.scene_visual") == [
        {
            "scene_id": new_ids[1],
            "template_id": "number_counter",
            "params": {"value": "11 pm", "label": "dinner time"},
        }
    ]
    for body in ({"template_id": "ken_burns_photo", "params": {}},
                 {"template_id": "kinetic_title", "params": {"text": "x" * 200}}):  # fmt: skip
        assert client.put(scene_url, json=body, headers=idem(h)).status_code == 422
    old_scene = f"/api/v1/projects/{project.id}/scenes/{scenes[1].id}/visual"  # version 1: not the latest
    assert client.put(old_scene, json={"template_id": "kinetic_title", "params": {"text": "x"}},
                      headers=idem(h)).status_code == 404  # fmt: skip

    # Make the visuals again (no state change).
    again = client.post(f"/api/v1/projects/{project.id}/commands/retry-visuals", headers=idem(h))
    assert again.status_code == 202 and jobs(env, "content.visuals") == [{"project_id": str(project.id)}]
    assert (
        client.post(f"/api/v1/projects/{project.id}/commands/retry-storyboard", headers=idem(h)).status_code
        == 409
    )


def test_no_storyboard_yet_and_not_editable_later(
    api: tuple[TestClient, dict[str, str]], db: Session
) -> None:
    client, h = api
    project, _ = project_with_storyboard(db, state="ASSEMBLY")
    got = client.get(f"/api/v1/projects/{project.id}/storyboard", headers=h).json()
    assert got["version"] == 1 and not got["editable"]
    refused = client.put(f"/api/v1/projects/{project.id}/storyboard",
                         json={"based_on_version": 1, "scenes": [{"id": str(uuid.uuid4()), "visual_instruction": "x"}]},
                         headers=idem(h))  # fmt: skip
    assert refused.status_code == 409 and refused.json()["code"] == "NOT_EDITABLE"
    ch = db.get_one(Channel, project.channel_id)
    empty = VideoProject(id=uuid7(), channel_id=ch.id, working_title="Fresh", format="SHORT",
                         state="STORYBOARDING", target_duration_s=45, render_profile={})  # fmt: skip
    db.add(empty)
    db.commit()
    fresh = client.get(f"/api/v1/projects/{empty.id}/storyboard", headers=h).json()
    assert fresh["version"] is None and fresh["scenes"] == [] and not fresh["editable"]
