"""Storyboard Studio (page 12) and Visual Studio (page 14) — Phase 8 step B.

- ``GET /projects/{id}/storyboard``: the latest storyboard version, its scenes with their pictures,
  the template registry, and the storyboard/visuals job that is running (if any).
- ``PUT /projects/{id}/storyboard``: the owner's changes to what each scene shows (visual idea,
  on-screen text, style) become a **new version**. Narration is never editable here: it is the locked
  script word for word (change the script by reopening it).
- ``PUT /projects/{id}/scenes/{scene_id}/visual``: the owner picks another template or text for one
  scene; a ``media.scene_visual`` job draws it (heavy work stays in workers).

Making the storyboard or the visuals again uses the project commands ``retry-storyboard`` and
``retry-visuals``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from tubeforge_agents.content_agents import STYLES
from tubeforge_agents.storyboard import (
    OWNER_EDIT_STATES,
    SceneEditError,
    clean_params,
    latest_storyboard,
    next_storyboard_version,
    owner_scene_check,
    scenes_of,
)
from tubeforge_media import templates as tpl

from tubeforge.api.deps import Db
from tubeforge.api.errors import ProblemError, not_found, problem_doc
from tubeforge.api.idempotency import Idempotency
from tubeforge.api.v1.pipeline import JobProgressOut, job_out
from tubeforge.api.v1.projects import Edit, QueuedOut, View, _audit, _project
from tubeforge.db.ids import uuid7
from tubeforge.db.models import JobProgress, Scene, Storyboard
from tubeforge.queue import defer_in_transaction
from tubeforge.research import forbidden

router = APIRouter(tags=["storyboards"])
WRITE: dict[int | str, dict[str, Any]] = {
    409: problem_doc("NOT_EDITABLE / NO_STORYBOARD"),
    412: problem_doc("VERSION_CONFLICT: changed elsewhere"),
    422: problem_doc("SCENE_INVALID / VALIDATION_ERROR / IDEMPOTENCY_MISMATCH"),
}
JOBS = ("content.storyboard", "content.visuals", "media.scene_visual")
Style = Literal["kinetic_text", "motion_graphics", "chart", "photo", "owner_footage", "screen_recording"]
assert set(STYLES) == set(Style.__args__)  # type: ignore[attr-defined]


class SceneOut(BaseModel):
    id: uuid.UUID
    position: int
    narration: str = Field(description="The locked script's words for this scene (not editable here).")
    visual_instruction: str
    on_screen_text: str | None
    duration_s: float = Field(description="Measured from the words at the speaking rate.")
    style: str | None
    is_hook: bool
    pattern_interrupt: bool
    treatment: str | None
    template_id: str | None
    template_label: str | None
    template_params: dict[str, Any] = Field(description="The template's fields (TubeForge's notes removed).")
    note: str | None = Field(description="Why TubeForge changed the visual agent's choice, if it did.")
    chart_claim_ids: list[str]
    stock_search_terms: list[str] = Field(description="Ideas for your own search later; nothing is bought.")
    visual_url: str | None = Field(description="The scene's drawn picture (it has a rights record).")


class TemplateOut(BaseModel):
    id: str
    label: str
    treatment: str
    use_for: str
    needs_media: bool
    fields: dict[str, Any]


class StoryboardOut(BaseModel):
    project_id: uuid.UUID
    project_state: str
    working_title: str
    format: str
    target_duration_s: int
    version: int | None = Field(description="None until the first storyboard is made.")
    author_type: str | None
    script_version_id: uuid.UUID | None
    created_at: datetime | None
    total_duration_s: float
    editable: bool
    scenes: list[SceneOut]
    templates: list[TemplateOut]
    job: JobProgressOut | None


class SceneEditIn(BaseModel):
    id: uuid.UUID
    visual_instruction: Annotated[str, Field(min_length=1, max_length=1000)]
    on_screen_text: Annotated[str, Field(max_length=120)] | None = None
    style: Style = "kinetic_text"


class StoryboardIn(BaseModel):
    based_on_version: int
    scenes: list[SceneEditIn] = Field(min_length=1, max_length=200)


class SceneVisualIn(BaseModel):
    template_id: Annotated[str, Field(max_length=40)]
    params: dict[str, Any]


def _templates() -> list[TemplateOut]:
    return [
        TemplateOut(
            id=t.id,
            label=t.label,
            treatment=t.treatment,
            use_for=t.use_for,
            needs_media=t.needs_media,
            fields=t.params.model_json_schema().get("properties", {}),
        )
        for t in tpl.REGISTRY.values()
    ]


def _scene_out(s: Scene) -> SceneOut:
    raw = s.template_params or {}
    template = tpl.REGISTRY.get(s.template_id or "")
    return SceneOut(
        id=s.id,
        position=s.position,
        narration=s.narration,
        visual_instruction=s.visual_instruction,
        on_screen_text=s.on_screen_text,
        duration_s=float(s.duration_s),
        style=s.style,
        is_hook=s.is_hook,
        pattern_interrupt=s.pattern_interrupt,
        treatment=s.treatment,
        template_id=s.template_id,
        template_label=template.label if template else None,
        template_params=clean_params(raw),
        note=str(raw.get("_why") or "") or None,
        chart_claim_ids=[str(c) for c in raw.get("_chart_claim_ids", [])],
        stock_search_terms=[str(t) for t in raw.get("_stock_search_terms", [])],
        visual_url=f"/api/v1/assets/{s.visual_asset_id}/download" if s.visual_asset_id else None,
    )


def _job(db: Session, project_id: uuid.UUID) -> JobProgressOut | None:
    now = datetime.now(UTC)
    row = db.scalar(
        select(JobProgress)
        .where(JobProgress.project_id == project_id, JobProgress.kind.in_(JOBS))
        .order_by(JobProgress.queued_at.desc())
        .limit(1)
    )
    if row is None or (row.finished_at is not None and now - row.finished_at > timedelta(minutes=10)):
        return None
    return job_out(db, row, now, {})


def storyboard_out(db: Session, project_id: uuid.UUID) -> StoryboardOut:
    project = _project(db, project_id)
    board = latest_storyboard(db, project.id)
    scenes = scenes_of(db, board.id) if board else []
    return StoryboardOut(
        project_id=project.id,
        project_state=project.state,
        working_title=project.working_title,
        format=project.format,
        target_duration_s=project.target_duration_s,
        version=board.version if board else None,
        author_type=board.author_type if board else None,
        script_version_id=board.script_version_id if board else None,
        created_at=board.created_at if board else None,
        total_duration_s=round(float(sum((s.duration_s for s in scenes), Decimal(0))), 1),
        editable=board is not None and project.state in OWNER_EDIT_STATES,
        scenes=[_scene_out(s) for s in scenes],
        templates=_templates(),
        job=_job(db, project.id),
    )


def _editable(db: Session, project_id: uuid.UUID) -> tuple[Any, Storyboard]:
    project = _project(db, project_id, lock=True)
    if project.state not in OWNER_EDIT_STATES:
        raise ProblemError(
            409,
            "NOT_EDITABLE",
            "Not editable",
            f"The storyboard cannot be changed while the project is {project.state}.",
        )
    board = latest_storyboard(db, project.id)
    if board is None:
        raise ProblemError(409, "NO_STORYBOARD", "No storyboard", "Wait for the first storyboard.")
    return project, board


@router.get("/projects/{project_id}/storyboard", response_model=StoryboardOut)
def get_storyboard(project_id: uuid.UUID, db: Db, p: View) -> StoryboardOut:
    return storyboard_out(db, project_id)


@router.put("/projects/{project_id}/storyboard", response_model=StoryboardOut, responses=WRITE)
def save_storyboard(project_id: uuid.UUID, body: StoryboardIn, request: Request, db: Db, p: Edit) -> Any:
    """The owner's scene changes become a new storyboard version; pictures stay with their scenes."""
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    project, board = _editable(db, project_id)
    if body.based_on_version != board.version:
        raise ProblemError(
            412, "VERSION_CONFLICT", "Changed elsewhere",
            f"Version {board.version} is the latest; reload it first.", current_version=board.version,
        )  # fmt: skip
    current = scenes_of(db, board.id)
    edits = {e.id: e for e in body.scenes}
    if set(edits) != {s.id for s in current}:
        raise ProblemError(422, "SCENE_INVALID", "Scenes changed", "Send every scene of the latest version.")
    for e in edits.values():
        if e.on_screen_text and forbidden.scan(e.on_screen_text):
            raise ProblemError(
                422, "SCENE_INVALID", "Not allowed", "On-screen text makes a promise TubeForge cannot keep."
            )

    def text(e: SceneEditIn) -> str | None:
        return (e.on_screen_text or "").strip() or None

    changed = [
        s for s in current
        if (s.visual_instruction, s.on_screen_text or None, s.style)
        != (edits[s.id].visual_instruction, text(edits[s.id]), edits[s.id].style)
    ]  # fmt: skip
    if not changed:
        out = storyboard_out(db, project.id)
        idem.store(200, out.model_dump(mode="json"))
        db.commit()
        return out
    new = Storyboard(
        id=uuid7(),
        project_id=project.id,
        channel_id=project.channel_id,
        version=next_storyboard_version(db, project.id),
        script_version_id=board.script_version_id,
        author_type="OWNER",
    )
    db.add(new)
    db.flush()
    for s in current:
        e = edits[s.id]
        db.add(
            Scene(
                id=uuid7(), storyboard_id=new.id, position=s.position, narration=s.narration,
                visual_instruction=e.visual_instruction, on_screen_text=text(e), duration_s=s.duration_s,
                style=e.style, is_hook=s.is_hook, pattern_interrupt=s.pattern_interrupt,
                treatment=s.treatment, template_id=s.template_id, template_params=s.template_params,
                visual_asset_id=s.visual_asset_id,
            )
        )  # fmt: skip
    db.flush()
    _audit(
        request, db, p, "storyboard.version_saved", project, version=new.version, scenes_changed=len(changed)
    )
    out = storyboard_out(db, project.id)
    idem.store(200, out.model_dump(mode="json"))
    db.commit()
    return out


@router.put(
    "/projects/{project_id}/scenes/{scene_id}/visual",
    response_model=QueuedOut,
    status_code=202,
    responses=WRITE,
)
def change_scene_visual(
    project_id: uuid.UUID, scene_id: uuid.UUID, body: SceneVisualIn, request: Request, db: Db, p: Edit
) -> Any:
    """The owner picks another template (or text) for one scene; a job draws the new picture."""
    idem = Idempotency(db, request, p.user.id, {"scene": str(scene_id), **body.model_dump(mode="json")})
    if (replayed := idem.replay()) is not None:
        return replayed
    project, board = _editable(db, project_id)
    scene = db.get(Scene, scene_id)
    if scene is None or scene.storyboard_id != board.id:
        raise not_found("No such scene in the latest storyboard.")
    try:
        checked = owner_scene_check(body.template_id, body.params)
    except SceneEditError as exc:
        raise ProblemError(422, "SCENE_INVALID", "Not usable", str(exc)) from exc
    job = defer_in_transaction(
        db,
        "media.scene_visual",
        queue="heavy",
        args={"scene_id": str(scene.id), "template_id": body.template_id, "params": checked.model_dump()},
    )
    _audit(
        request, db, p, "scene.visual_changed", project, scene=scene.position, template_id=body.template_id
    )
    out = QueuedOut(job_id=job)
    idem.store(202, out.model_dump(mode="json"))
    db.commit()
    return out
