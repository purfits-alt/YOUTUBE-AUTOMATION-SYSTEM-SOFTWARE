"""Storyboard and scene visuals (Phase 8 step B): locked script → scenes (A12) → one template and one
keyframe per scene (A13 + the procedural renderer). Run in workers, never in the API. The model plans;
code checks.

- :func:`run_storyboard` — the locked script is split into numbered sentences **in code**; A12 only
  groups them. Narration is joined from the sentences, so it is the approved script word for word, and
  every scene's duration is measured from its words at the speaking rate. Scene 1 is always exactly
  the hook; scenes holding a re-hook line are pattern interrupts. An answer that skips, repeats or
  reorders sentences gets one repair call; if that fails too, code cuts the scenes itself, so the
  project never stalls here. Then ``storyboard_done`` → ASSET_GENERATION and ``content.visuals``.
- :func:`run_visuals` — A13 proposes a template per scene; code keeps only registry templates whose
  parameters validate, charts whose every number appears in the cited brief claims, no forbidden
  phrase, the soft reminder only at the end; anything else falls back to a text template. No template
  covers more than 40 % of the scenes, a pattern interrupt never repeats the template before it, and
  the opening differs from the channel's last 5 videos. Each scene's keyframe is drawn with the
  channel brand and stored as a PROCEDURAL asset with a SYSTEM_GENERATED rights record. Then
  ``assets_ready`` (all scenes have a rights-cleared visual) → VOICEOVER.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tubeforge_media import templates as tpl
from tubeforge_media.channel_art import FONT, Brand, brand_from, png

from tubeforge import progress
from tubeforge.assets import Rights, add_asset
from tubeforge.audit import Actor
from tubeforge.content import craft
from tubeforge.db.ids import uuid7
from tubeforge.db.models import (
    Channel,
    ResearchBrief,
    Scene,
    ScriptVersion,
    Storyboard,
    VideoProject,
)
from tubeforge.gateway.core import Gateway
from tubeforge.logging import get_logger
from tubeforge.notifications import notify_owners
from tubeforge.orchestrator import engine
from tubeforge.orchestrator.machines import MACHINES
from tubeforge.queue import defer_in_transaction
from tubeforge.research import forbidden
from tubeforge.research.wiki_articles import LANGUAGES
from tubeforge_agents.base import run_agent
from tubeforge_agents.content_agents import A12, A13, STYLES
from tubeforge_agents.discovery import PipelineError, _outcome_error, channel_blueprint

log = get_logger("tubeforge.storyboard")

ORCH = Actor("ORCH", "orchestrator")
RENDERER = "tubeforge_media.templates v1"
SENTENCE_END = re.compile(r"(?<=[.!?…])[\"”’)]*\s+")
#: Code-cut scenes: a new scene once this many seconds of speech are in it (long-form, Short).
TARGET_SCENE_S = {"LONG": 12.0, "SHORT": 3.0}
MAX_SHARE = 0.40
#: Text templates a scene can always switch to (their parameters come from the scene's own words).
TEXT_TEMPLATES = ("kinetic_title", "lower_third", "quote_card")
BOLD_OPENERS = ("kinetic_title", "number_counter", "split_compare")
CHARTS = ("bar_chart", "line_chart", "pie_chart", "number_counter")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


# ------------------------------------------------------------------------------------ sentences
@dataclass(frozen=True)
class Sentence:
    id: str
    text: str
    hook: bool
    part: int  # index of the spoken part (hook, sections…, payoff, CTA): scenes may span parts


def _split(text: str) -> list[str]:
    clean = craft.OWNER_SLOT.sub("", text)
    return [s.strip() for s in SENTENCE_END.split(clean) if s.strip()]


def sentences(body: dict[str, Any]) -> list[Sentence]:
    """The locked script's spoken text as numbered sentences, in reading order (the hook first)."""
    out: list[Sentence] = []
    hook = str(body.get("hook", {}).get("text", ""))
    parts = [hook, *[str(s.get("text", "")) for s in body.get("sections", [])]]
    parts += [str(body.get("payoff", "")), str(body.get("cta", ""))]
    for index, part in enumerate(parts):
        for text in _split(part):
            out.append(Sentence(f"s{len(out)}", text, index == 0 and bool(hook.strip()), index))
    return out


def seconds(text: str, wpm: int) -> Decimal:
    return Decimal(str(max(0.5, round(craft.words(text) * 60 / max(wpm, 1), 2))))


# --------------------------------------------------------------------------------------- cutting
@dataclass
class Cut:
    first: int
    last: int
    visual_instruction: str = "Key words of the narration on screen."
    on_screen_text: str | None = None
    style: str = "kinetic_text"
    pattern_interrupt: bool = False


def check_cut(answer: list[dict[str, Any]], sents: list[Sentence]) -> tuple[list[Cut] | None, str]:
    """The model's scenes as ranges, or None and why (every sentence once, in order)."""
    index = {s.id: i for i, s in enumerate(sents)}
    expected, cuts = 0, []
    for n, scene in enumerate(answer, start=1):
        a, b = index.get(str(scene.get("first"))), index.get(str(scene.get("last")))
        if a is None or b is None:
            return None, f"scene {n} names a sentence id that does not exist"
        if a != expected or b < a:
            return (
                None,
                f"scene {n} must start at s{expected} and end at or after it (every sentence once, in order)",
            )
        text = scene.get("on_screen_text")
        style = str(scene.get("style"))
        cuts.append(
            Cut(
                a,
                b,
                str(scene.get("visual_instruction") or Cut.visual_instruction)[:1000],
                str(text).strip()[:120] if text and str(text).strip() else None,
                style if style in STYLES else "kinetic_text",
                bool(scene.get("pattern_interrupt")),
            )
        )
        expected = b + 1
    if expected != len(sents):
        return None, f"sentences s{expected}–s{len(sents) - 1} are in no scene"
    return cuts, ""


def with_hook_scene(cuts: list[Cut], sents: list[Sentence]) -> list[Cut]:
    """Scene 1 is exactly the hook: cuts inside the hook are merged, a cut is added where it ends."""
    n_hook = sum(1 for s in sents if s.hook)
    if n_hook == 0 or n_hook >= len(sents):
        return cuts
    starts = sorted({c.first for c in cuts if not 0 < c.first < n_hook} | {0, n_hook})
    out: list[Cut] = []
    for k, start in enumerate(starts):
        end = starts[k + 1] - 1 if k + 1 < len(starts) else len(sents) - 1
        source = next(c for c in cuts if c.first <= start <= c.last)
        out.append(
            Cut(start, end, source.visual_instruction, source.on_screen_text, source.style,
                source.pattern_interrupt and source.first == start)
        )  # fmt: skip
    return out


def auto_cut(sents: list[Sentence], fmt: str, wpm: int) -> list[Cut]:
    """Scenes cut by code (the model's answers were unusable twice): the hook, then about 12 s (3 s
    for Shorts) of speech per scene, never across a part of the script."""
    target = TARGET_SCENE_S.get(fmt, 12.0)
    cuts: list[Cut] = []
    start, spoken = 0, 0.0
    for i, s in enumerate(sents):
        spoken += float(seconds(s.text, wpm))
        nxt = sents[i + 1] if i + 1 < len(sents) else None
        boundary = nxt is None or nxt.part != s.part or (s.hook and not nxt.hook)
        if boundary or (spoken >= target and not s.hook):
            cuts.append(Cut(start, i))
            start, spoken = i + 1, 0.0
    return cuts


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def mark_rehooks(cuts: list[Cut], sents: list[Sentence], re_hooks: list[str]) -> None:
    """A scene that holds a re-hook line is a pattern interrupt (the visual changes sharply there)."""
    for cut in cuts[1:]:
        narration = _norm(" ".join(s.text for s in sents[cut.first : cut.last + 1]))
        if any(len(h) >= 12 and h[:40] in narration for h in map(_norm, re_hooks)):
            cut.pattern_interrupt = True


# ------------------------------------------------------------------------------------ storyboard
@dataclass
class StoryboardResult:
    storyboard: Storyboard
    scenes: list[Scene]
    cut_by: str  # AGENT | REPAIRED | CODE


def _locked(db: Session, project: VideoProject) -> ScriptVersion:
    if project.locked_script_version_id is None:
        raise PipelineError(
            "FAILED", "Approve the script first: the storyboard is cut from the locked script."
        )
    return db.get_one(ScriptVersion, project.locked_script_version_id)


def _language(channel: Channel) -> str:
    return channel.content_language if channel.content_language in LANGUAGES else "en"


def next_storyboard_version(db: Session, project_id: uuid.UUID) -> int:
    current = db.scalar(
        select(func.coalesce(func.max(Storyboard.version), 0)).where(Storyboard.project_id == project_id)
    )
    return int(current or 0) + 1


def latest_storyboard(db: Session, project_id: uuid.UUID) -> Storyboard | None:
    return db.scalar(
        select(Storyboard)
        .where(Storyboard.project_id == project_id)
        .order_by(Storyboard.version.desc())
        .limit(1)
    )


def scenes_of(db: Session, storyboard_id: uuid.UUID) -> list[Scene]:
    return list(
        db.scalars(select(Scene).where(Scene.storyboard_id == storyboard_id).order_by(Scene.position))
    )


def run_storyboard(
    db: Session,
    gateway: Gateway,
    project_id: uuid.UUID,
    *,
    wpm: int = craft.DEFAULT_WPM,
    now: datetime | None = None,
) -> StoryboardResult:
    project = db.get_one(VideoProject, project_id)
    if project.state != "STORYBOARDING":
        raise PipelineError("FAILED", f"The project is {project.state}, not STORYBOARDING.")
    version = _locked(db, project)
    sents = sentences(version.body)
    if not sents:
        raise PipelineError("FAILED", "The locked script has no spoken text.")
    channel = db.get_one(Channel, project.channel_id)
    re_hooks = [str(r.get("text", ""))[:300] for r in version.body.get("re_hooks", [])][:20]
    data: dict[str, Any] = {
        "language": _language(channel),
        "format": project.format,
        "title": project.working_title,
        "sentences": [{"id": s.id, "text": s.text[:1500], "hook": s.hook} for s in sents],
        "re_hooks": re_hooks,
    }

    def ask(fix: str) -> list[dict[str, Any]]:
        out = run_agent(
            db, gateway, A12, {**data, "fix_notes": fix},
            channel_id=project.channel_id, project_id=project.id, idempotent=False, now=now,
        )  # fmt: skip
        if out.data is None:
            raise _outcome_error(out)
        return list(out.data.get("scenes", []))

    progress.report(10, "Cutting the script into scenes")
    cuts, why = check_cut(ask(""), sents)
    cut_by = "AGENT"
    if cuts is None:
        progress.report(40, "Fixing the scene cuts")
        log.info("storyboard.repair", project_id=str(project.id), why=why)
        cuts, why = check_cut(ask(why), sents)
        cut_by = "REPAIRED"
    if cuts is None:
        log.info("storyboard.code_cut", project_id=str(project.id), why=why)
        cuts, cut_by = auto_cut(sents, project.format, wpm), "CODE"
    cuts = with_hook_scene(cuts, sents)
    mark_rehooks(cuts, sents, re_hooks)
    progress.report(70, "Saving the scenes")
    board = Storyboard(
        id=uuid7(),
        project_id=project.id,
        channel_id=project.channel_id,
        version=next_storyboard_version(db, project.id),
        script_version_id=version.id,
        author_type="AGENT",
    )
    db.add(board)
    db.flush()
    rows: list[Scene] = []
    for position, cut in enumerate(cuts, start=1):
        narration = " ".join(s.text for s in sents[cut.first : cut.last + 1])
        on_screen = (
            cut.on_screen_text if cut.on_screen_text and not forbidden.scan(cut.on_screen_text) else None
        )
        row = Scene(
            id=uuid7(),
            storyboard_id=board.id,
            position=position,
            narration=narration,
            visual_instruction=cut.visual_instruction,
            on_screen_text=on_screen,
            duration_s=seconds(narration, wpm),
            style=cut.style,
            is_hook=position == 1,
            pattern_interrupt=cut.pattern_interrupt and position > 1,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    engine.transition(
        db, MACHINES["video_project"], project.id, "storyboard_done", actor=Actor("AGENT", A12.code),
        payload={"scenes": len(rows), "cut_by": cut_by},
        idempotency_key=f"storyboard-done:{board.id}", now=now,
    )  # fmt: skip
    defer_in_transaction(db, "content.visuals", queue="heavy", args={"project_id": str(project.id)})
    db.commit()
    return StoryboardResult(board, rows, cut_by)


# --------------------------------------------------------------------------------------- visuals
@dataclass
class Choice:
    template_id: str
    params: BaseModel
    why: str = ""  # why code changed A13's choice (empty = kept)
    chart_claim_ids: list[str] = field(default_factory=list)
    stock_search_terms: list[str] = field(default_factory=list)


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:—-")
    return (cut or text[: limit - 1]) + "…"


def text_params(template_id: str, scene: Scene) -> BaseModel:
    """Parameters for a text template, from the scene's own words (always valid)."""
    parts = _split(scene.narration)
    first = parts[0] if parts else scene.narration.strip()
    words = scene.on_screen_text or first or "…"
    params: dict[str, Any]
    if template_id == "lower_third":
        params = {"title": _clip(words, 60)}
    elif template_id == "quote_card":
        params = {"quote": _clip(first or words, 200)}
    else:
        template_id, params = "kinetic_title", {"text": _clip(words, 80)}
    checked = tpl.validate(template_id, params)
    assert checked is not None
    return checked


def numbers(text: str) -> set[float]:
    out: set[float] = set()
    for raw in NUMBER.findall(text):
        value = raw.replace(",", "") if re.fullmatch(r"\d{1,3}(?:,\d{3})+", raw) else raw.replace(",", ".")
        try:
            out.add(float(value))
        except ValueError:
            continue
    return out


def chart_numbers(template_id: str, params: BaseModel) -> set[float]:
    data = params.model_dump()
    if template_id == "number_counter":
        return numbers(str(data.get("value", "")))
    return {float(v) for v in data.get("values", [])}


def choose(
    proposal: dict[str, Any] | None,
    scene: Scene,
    *,
    last: bool,
    claims: dict[str, str],
) -> Choice:
    """Keep A13's template for one scene only if every rule holds; otherwise a text template."""
    fallback = (
        tpl.FALLBACK if scene.is_hook else ("quote_card" if len(scene.narration) > 160 else "lower_third")
    )

    def plain(why: str) -> Choice:
        return Choice(fallback, text_params(fallback, scene), why)

    if not proposal:
        return plain("no template proposed")
    template_id = str(proposal.get("template_id", ""))
    terms = [_clip(str(t), 60) for t in proposal.get("stock_search_terms", []) if str(t).strip()][:3]
    template = tpl.REGISTRY.get(template_id)
    if template is None:
        return plain(f"{template_id!r} is not in the template registry")
    if template.needs_media:
        return plain(f"{template_id} needs your own media (uploads arrive later)")
    params = tpl.validate(template_id, proposal.get("params"))
    if params is None:
        return plain(f"the parameters for {template_id} did not fit")
    if forbidden.scan(params.model_dump()):
        return plain("the on-screen text made a promise TubeForge cannot keep")
    if template_id == "subscribe_reminder_soft" and not last:
        return plain("the soft reminder belongs at the end")
    cited = [str(c) for c in proposal.get("chart_claim_ids", []) if str(c) in claims][:6]
    if template_id in CHARTS:
        stated = set().union(*(numbers(claims[c]) for c in cited)) if cited else set()
        if not cited or not chart_numbers(template_id, params) <= stated:
            return plain("a chart number is not in the cited brief claims")
    return Choice(template_id, params, "", cited if template_id in CHARTS else [], terms)


def rebalance(choices: list[Choice], scenes: list[Scene], recent: list[list[str]]) -> None:
    """Variety rules, in code: ≤ 40 % per template, a pattern interrupt changes the template, and the
    opening differs from the channel's last 5 videos."""
    n = len(choices)
    limit = max(1, math.floor(MAX_SHARE * n)) if n >= 5 else 2

    def count(template_id: str) -> int:
        return sum(1 for c in choices if c.template_id == template_id)

    def switch(i: int, why: str) -> bool:
        around = {choices[j].template_id for j in (i - 1, i + 1) if 0 <= j < n}
        for alt in TEXT_TEMPLATES:
            if alt != choices[i].template_id and alt not in around and count(alt) < limit:
                choices[i] = Choice(alt, text_params(alt, scenes[i]), why)
                return True
        return False

    for template_id in {c.template_id for c in choices}:
        for i in reversed(range(1, n)):
            if count(template_id) <= limit:
                break
            if choices[i].template_id == template_id:
                switch(i, "variety: no template on more than 40 % of the scenes")
    for i in range(1, n):
        if scenes[i].pattern_interrupt and choices[i].template_id == choices[i - 1].template_id:
            switch(i, "variety: a pattern interrupt changes the picture")
    if choices and choices[0].template_id not in BOLD_OPENERS:
        choices[0] = Choice(tpl.FALLBACK, text_params(tpl.FALLBACK, scenes[0]), "the hook gets a bold title")
    openings = {tuple(seq[:5]) for seq in recent if len(seq) >= min(5, n)}
    for i in range(1, min(5, n)):
        if tuple(c.template_id for c in choices[:5]) not in openings:
            break
        switch(i, "variety: the opening differs from your recent videos")


def recent_sequences(
    db: Session, channel_id: uuid.UUID, exclude: uuid.UUID, limit: int = 5
) -> list[list[str]]:
    """Template order of the channel's last 5 other videos (A13 must not repeat it)."""
    boards = db.scalars(
        select(Storyboard)
        .where(Storyboard.channel_id == channel_id, Storyboard.project_id != exclude)
        .order_by(Storyboard.created_at.desc())
    )
    out: list[list[str]] = []
    seen: set[uuid.UUID] = set()
    for board in boards:
        if board.project_id in seen:
            continue
        seq = [s.template_id for s in scenes_of(db, board.id) if s.template_id]
        if seq:
            seen.add(board.project_id)
            out.append(seq[:40])
        if len(out) >= limit:
            break
    return out


def _brief_claims(db: Session, project_id: uuid.UUID) -> list[dict[str, str]]:
    brief = db.scalar(
        select(ResearchBrief)
        .where(ResearchBrief.project_id == project_id, ResearchBrief.status == "APPROVED")
        .order_by(ResearchBrief.version.desc())
        .limit(1)
    )
    return [
        {"id": str(c.get("id", ""))[:10], "text": str(c.get("text", ""))[:400]}
        for c in (brief.content.get("claims", []) if brief else [])
        if c.get("verdict") in (None, "SUPPORTED")
    ][:40]


def channel_brand(db: Session, channel: Channel) -> Brand:
    strategy = channel_blueprint(db, channel.id)
    return brand_from(strategy.blueprint if strategy else {}, channel.name, None)


def scene_rights(scene: Scene, choice: Choice, brand: Brand) -> Rights:
    return Rights(
        basis="SYSTEM_GENERATED",
        licence_name="Drawn by TubeForge from your brand colours; font Source Sans Pro (SIL OFL 1.1)",
        licence_url=FONT["licence_url"],
        commercial_use_allowed=True,
        lineage={
            "renderer": RENDERER,
            "font": FONT,
            "template_id": choice.template_id,
            "scene_id": str(scene.id),
            "storyboard_id": str(scene.storyboard_id),
            "palette": brand.palette,
            "chart_claim_ids": choice.chart_claim_ids,
        },
    )


def draw_scene(
    db: Session, data_dir: Path, project: VideoProject, scene: Scene, choice: Choice, brand: Brand
) -> None:
    """Draw one scene's keyframe and attach it (a PROCEDURAL asset with its rights record)."""
    frame = tpl.render(choice.template_id, choice.params, brand, project.format)
    asset = add_asset(
        db,
        data_dir,
        png(frame.image),
        mime_type="image/png",
        kind="IMAGE",
        origin="PROCEDURAL",
        rights=scene_rights(scene, choice, brand),
        created_by=("SYSTEM", RENDERER),
        channel_id=project.channel_id,
        project_id=project.id,
        width=frame.image.width,
        height=frame.image.height,
    )
    scene.treatment = tpl.REGISTRY[choice.template_id].treatment
    scene.template_id = choice.template_id
    scene.template_params = {
        **choice.params.model_dump(),
        "_why": choice.why,
        "_chart_claim_ids": choice.chart_claim_ids,
        "_stock_search_terms": choice.stock_search_terms,
    }
    scene.visual_asset_id = asset.id


def clean_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """A scene's template parameters without TubeForge's own notes (keys starting with ``_``)."""
    return {k: v for k, v in (params or {}).items() if not k.startswith("_")}


@dataclass
class VisualsResult:
    scenes: list[Scene]
    changed: int  # scenes where code replaced A13's choice


def run_visuals(
    db: Session,
    gateway: Gateway,
    data_dir: Path,
    project_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> VisualsResult:
    project = db.get_one(VideoProject, project_id)
    if project.state != "ASSET_GENERATION":
        raise PipelineError("FAILED", f"The project is {project.state}, not ASSET_GENERATION.")
    board = latest_storyboard(db, project.id)
    if board is None:
        raise PipelineError("FAILED", "There is no storyboard yet.")
    scenes = scenes_of(db, board.id)
    if not scenes:
        raise PipelineError("FAILED", "The storyboard has no scenes.")
    channel = db.get_one(Channel, project.channel_id)
    claims = _brief_claims(db, project.id)
    recent = recent_sequences(db, project.channel_id, project.id)
    progress.report(10, "Choosing a picture for each scene")
    outcome = run_agent(
        db,
        gateway,
        A13,
        {
            "language": _language(channel),
            "format": project.format,
            "scenes": [
                {
                    "scene_id": f"scene{s.position}",
                    "narration": s.narration[:1500],
                    "on_screen_text": s.on_screen_text,
                    "visual_instruction": s.visual_instruction[:1000],
                    "style": s.style or "kinetic_text",
                    "is_hook": s.is_hook,
                    "pattern_interrupt": s.pattern_interrupt,
                }
                for s in scenes[:80]
            ],
            "claims": claims,
            "templates": tpl.describe(),
            "recent_sequences": recent,
        },
        channel_id=project.channel_id,
        project_id=project.id,
        idempotent=False,
        now=now,
    )
    if outcome.data is None:
        raise _outcome_error(outcome)
    proposals = {str(p.get("scene_id")): p for p in outcome.data.get("scenes", [])}
    by_id = {c["id"]: c["text"] for c in claims}
    choices = [
        choose(proposals.get(f"scene{s.position}"), s, last=s.position >= len(scenes) - 1, claims=by_id)
        for s in scenes
    ]
    rebalance(choices, scenes, recent)
    brand = channel_brand(db, channel)
    for i, (scene, choice) in enumerate(zip(scenes, choices, strict=True)):
        progress.report(30 + 65 * i // len(scenes), f"Drawing scene {i + 1} of {len(scenes)}")
        draw_scene(db, data_dir, project, scene, choice, brand)
    db.flush()
    missing = sum(1 for s in scenes if s.visual_asset_id is None)
    engine.transition(
        db, MACHINES["video_project"], project.id, "assets_ready", actor=ORCH,
        payload={"scenes_without_visual": missing, "unconfirmed_stock_purchases": 0},
        idempotency_key=f"assets-ready:{board.id}", now=now,
    )  # fmt: skip
    changed = sum(1 for c in choices if c.why)
    notify_owners(
        db,
        event_type="visuals.ready",
        severity="INFO",
        title="Storyboard and scene visuals ready",
        body=(
            f"“{project.working_title}”: {len(scenes)} scenes, each with a picture. "
            "Open the Visual Studio to change any of them."
        ),
        dedup_key=f"visuals-ready:{board.id}",
        channel_id=project.channel_id,
        link=f"/projects/{project.id}/visuals",
        entity_type="video_project",
        entity_id=project.id,
    )
    db.commit()
    return VisualsResult(scenes, changed)


# ------------------------------------------------------------------------------ owner's changes
#: The owner may change the storyboard and the pictures until video assembly starts (Phase 9).
OWNER_EDIT_STATES = {"STORYBOARDING", "ASSET_GENERATION", "VOICEOVER"}


class SceneEditError(ValueError):
    """The owner's change cannot be used (shown to the owner as is)."""


def owner_scene_check(template_id: str, params: dict[str, Any]) -> BaseModel:
    """The owner's own template choice for one scene: registry, parameters, no forbidden promise."""
    template = tpl.REGISTRY.get(template_id)
    if template is None:
        raise SceneEditError(f"There is no template called {template_id!r}.")
    if template.needs_media:
        raise SceneEditError(
            f"“{template.label}” needs your own photo or clip; uploads arrive in a later step."
        )
    checked = tpl.validate(template_id, params)
    if checked is None:
        raise SceneEditError(f"The fields for “{template.label}” do not fit; check the lengths and numbers.")
    if forbidden.scan(checked.model_dump()):
        raise SceneEditError("The text makes a promise TubeForge cannot keep (for example “guaranteed”).")
    return checked


def redraw_scene(
    db: Session, data_dir: Path, scene_id: uuid.UUID, template_id: str, params: dict[str, Any]
) -> Scene:
    """Draw one scene again with the template the owner chose (``media.scene_visual``)."""
    scene = db.get_one(Scene, scene_id)
    board = db.get_one(Storyboard, scene.storyboard_id)
    project = db.get_one(VideoProject, board.project_id)
    if project.state not in OWNER_EDIT_STATES:
        raise SceneEditError(f"Scenes cannot be changed while the project is {project.state}.")
    checked = owner_scene_check(template_id, params)
    progress.report(30, f"Drawing scene {scene.position}")
    channel = db.get_one(Channel, project.channel_id)
    draw_scene(
        db,
        data_dir,
        project,
        scene,
        Choice(template_id, checked, "chosen by you"),
        channel_brand(db, channel),
    )
    db.flush()
    return scene
