"""A08 Idea Generation, A09 Research, A10 Fact-Checking and A11 Scriptwriting (AGENT_PROMPTS v1.0/v1.1).

Every document, owner text, brief and recent title reaches the model only through the ``untrusted``
filter. Similarity, craft rules and durations are checked in code by the pipelines in
``tubeforge_agents.content``; the model's own numbers are never trusted.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

from tubeforge.db.models import Channel
from tubeforge_agents.base import AgentTask
from tubeforge_agents.discovery_agents import DOCS, DocIn, FixNotes, Language, _rules_and_fixes
from tubeforge_agents.prompting import render_user

Format = Literal["LONG", "SHORT"]
VariationKind = Literal["PART_2", "NEW_ANGLE", "UPDATE", "SHORT_FROM_LONG", "LONG_FROM_SHORT", "SERIES"]


class PackagingPromise(BaseModel):
    title_idea: str = Field(max_length=100)
    thumbnail_text_idea: str = Field(max_length=40)
    promise_statement: str = Field(max_length=200)


class TrendIn(BaseModel):
    id: str
    term: str = Field(max_length=120)
    pillar: str = Field(default="", max_length=60)


class VariationSource(BaseModel):
    title: str = Field(max_length=200)
    angle: str = Field(default="", max_length=500)
    format: Format = "LONG"
    kind: VariationKind


# ------------------------------------------------------------------------------------------ A08
class IdeaInput(BaseModel):
    language: Language = "en"
    count: int = Field(ge=1, le=20)
    pillars: list[str] = Field(min_length=1, max_length=7)
    channel_brief: str = Field(default="", max_length=1500)  # niche, positioning, audience, pillars
    format: Format | None = None  # None: rotate
    pillar: str | None = None
    recent_titles: list[str] = Field(default_factory=list, max_length=80)
    trends: list[TrendIn] = Field(default_factory=list, max_length=20)
    variation_of: VariationSource | None = None
    fix_notes: FixNotes = ""


class IdeaGenerationAgent(AgentTask):
    code: ClassVar[str] = "A08_IDEA_GENERATION"
    task_type: ClassVar[str] = "ideas"
    temperature: ClassVar[float] = 0.8
    max_output_tokens: ClassVar[int] = 6000
    input_model: ClassVar[type[BaseModel]] = IdeaInput

    def context(self, data: BaseModel, channel: Channel | None) -> dict[str, Any]:
        assert isinstance(data, IdeaInput)
        return {"channel_name": channel.name if channel else "", "language": data.language}

    def user_message(self, data: BaseModel) -> str:
        assert isinstance(data, IdeaInput)
        return render_user(
            "Count: {{ count }}. Format: {{ fmt }}. Pillar: {{ pillar }}.\n"
            "What this channel is about (every idea must fit it): {{ brief | untrusted('channel_brief') }}\n"
            "Channel pillars: {{ pillars | untrusted('pillars') }}\n"
            "Recent titles on this channel (do not repeat them): {{ recent | untrusted('recent_titles') }}\n"
            "Trends you may use (copy the id into trend_item_id): {{ trends | untrusted('trends') }}\n"
            "{% if variation %}Variation mode. Source video of the owner's own channel: "
            "{{ variation | untrusted('variation_source') }}\nEvery idea must be a {{ kind }} variation.\n"
            "{% endif %}{{ rules }}",
            {
                "count": data.count,
                "fmt": data.format or "rotate LONG and SHORT",
                "pillar": data.pillar or "spread across the pillars",
                "pillars": json.dumps(data.pillars, ensure_ascii=False),
                "brief": data.channel_brief or "(not given)",
                "recent": json.dumps(data.recent_titles, ensure_ascii=False),
                "trends": json.dumps([t.model_dump() for t in data.trends], ensure_ascii=False),
                "variation": data.variation_of.model_dump_json() if data.variation_of else "",
                "kind": data.variation_of.kind if data.variation_of else "",
                "rules": _rules_and_fixes(data.fix_notes),
            },
        )


# ------------------------------------------------------------------------------------------ A09
class IdeaBrief(BaseModel):
    title: str = Field(max_length=200)
    angle: str = Field(default="", max_length=500)
    format: Format = "LONG"
    packaging_promise: PackagingPromise | None = None


class ResearchInput(BaseModel):
    language: Language = "en"
    idea: IdeaBrief
    documents: list[DocIn] = Field(min_length=1, max_length=12)


class ResearchAgent(AgentTask):
    code: ClassVar[str] = "A09_RESEARCH"
    task_type: ClassVar[str] = "research"
    temperature: ClassVar[float] = 0.1
    max_output_tokens: ClassVar[int] = 6000
    input_model: ClassVar[type[BaseModel]] = ResearchInput

    def context(self, data: BaseModel, channel: Channel | None) -> dict[str, Any]:
        assert isinstance(data, ResearchInput)
        return {
            "channel_name": channel.name if channel else "",
            "language": data.language,
            "format": data.idea.format,
        }

    def user_message(self, data: BaseModel) -> str:
        assert isinstance(data, ResearchInput)
        return render_user(
            "Approved idea and packaging promise:\n{{ idea | untrusted('idea') }}\nSource documents:\n"
            + DOCS,
            {"idea": data.idea.model_dump_json(), "documents": [d.model_dump() for d in data.documents]},
        )


# ------------------------------------------------------------------------------------------ A10
class FactCheckInput(BaseModel):
    language: Language = "en"
    text: str = Field(min_length=1, max_length=40000)
    documents: list[DocIn] = Field(min_length=1, max_length=12)


class FactCheckingAgent(AgentTask):
    code: ClassVar[str] = "A10_FACT_CHECKING"
    task_type: ClassVar[str] = "research"
    temperature: ClassVar[float] = 0.0
    max_output_tokens: ClassVar[int] = 6000
    input_model: ClassVar[type[BaseModel]] = FactCheckInput

    def context(self, data: BaseModel, channel: Channel | None) -> dict[str, Any]:
        assert isinstance(data, FactCheckInput)
        return {"channel_name": channel.name if channel else "", "language": data.language}

    def user_message(self, data: BaseModel) -> str:
        assert isinstance(data, FactCheckInput)
        return render_user(
            "Text to check:\n{{ text | untrusted('text') }}\nSource documents:\n" + DOCS,
            {"text": data.text, "documents": [d.model_dump() for d in data.documents]},
        )


# ------------------------------------------------------------------------------------------ A11
class BriefClaim(BaseModel):
    id: str = Field(max_length=10)
    text: str = Field(max_length=400)


class StyleGuide(BaseModel):
    tone: str = Field(default="warm, direct, curious", max_length=200)
    humour: bool = False
    energy: Literal["CALM", "MEDIUM", "HIGH"] = "MEDIUM"


class ScriptInput(BaseModel):
    language: Language = "en"
    format: Format
    title: str = Field(max_length=200)
    packaging_promise: PackagingPromise
    summary: str = Field(default="", max_length=1200)
    claims: list[BriefClaim] = Field(min_length=1, max_length=40)
    suggested_structure: list[dict[str, str]] = Field(default_factory=list, max_length=10)
    hook_ideas: list[str] = Field(default_factory=list, max_length=5)
    value_add: dict[str, str] = Field(default_factory=dict)
    style_guide: StyleGuide = Field(default_factory=StyleGuide)
    target_duration_s: int = Field(ge=10, le=3600)
    wpm: int = Field(default=150, ge=80, le=220)
    recent_script_phrases: list[str] = Field(default_factory=list, max_length=40)
    current_draft: str = Field(default="", max_length=40000)  # the latest version, for an owner's redraft
    fix_notes: str = Field(default="", max_length=3000)  # set by the pipeline after failed checks


class ScriptwritingAgent(AgentTask):
    code: ClassVar[str] = "A11_SCRIPTWRITING"
    task_type: ClassVar[str] = "script_draft"
    temperature: ClassVar[float] = 0.7
    max_output_tokens: ClassVar[int] = 12000
    input_model: ClassVar[type[BaseModel]] = ScriptInput

    def context(self, data: BaseModel, channel: Channel | None) -> dict[str, Any]:
        assert isinstance(data, ScriptInput)
        return {
            "channel_name": channel.name if channel else "",
            "language": data.language,
            "format": data.format,
            "target_duration_s": data.target_duration_s,
            "wpm": data.wpm,
            "target_words": round(data.target_duration_s * data.wpm / 60),
            "humour": data.style_guide.humour,
        }

    def user_message(self, data: BaseModel) -> str:
        assert isinstance(data, ScriptInput)
        fixes = ""
        if data.fix_notes:
            fixes = (
                "\nNotes for this draft (an owner's instruction and/or checks your previous draft "
                f"failed): {data.fix_notes}\nWrite the whole script and follow every one of them."
            )
        return render_user(
            "Working title: {{ title | untrusted('title') }}\n"
            "Packaging promise (keep it): {{ promise | untrusted('packaging_promise') }}\n"
            "Brief summary: {{ summary | untrusted('brief_summary') }}\n"
            "Brief claims (cite their ids in fact_refs): {{ claims | untrusted('brief_claims') }}\n"
            "Suggested structure: {{ structure | untrusted('structure') }}\n"
            "Hook ideas: {{ hooks | untrusted('hook_ideas') }}\n"
            "Owner's value-add text (use verbatim in [[OWNER: …]] places): "
            "{{ value_add | untrusted('owner_value_add') }}\n"
            "Style guide: {{ style | untrusted('style_guide') }}\n"
            "Recent-script phrases to avoid: {{ recent | untrusted('recent_script_phrases') }}"
            "{% if draft %}\nCurrent draft (revise it; keep what the notes do not ask to change): "
            "{{ draft | untrusted('current_draft') }}{% endif %}{{ fixes }}",
            {
                "title": data.title,
                "promise": data.packaging_promise.model_dump_json(),
                "summary": data.summary or "(none)",
                "claims": json.dumps([c.model_dump() for c in data.claims], ensure_ascii=False),
                "structure": json.dumps(data.suggested_structure, ensure_ascii=False),
                "hooks": json.dumps(data.hook_ideas, ensure_ascii=False),
                "value_add": json.dumps(data.value_add, ensure_ascii=False) if data.value_add else "(none)",
                "style": data.style_guide.model_dump_json(),
                "recent": json.dumps(data.recent_script_phrases, ensure_ascii=False),
                "draft": data.current_draft,
                "fixes": fixes,
            },
        )


# --------------------------------------------------------------------- A11 · owner-part options
class OwnerPartInput(BaseModel):
    language: Language = "en"
    title: str = Field(max_length=200)
    prompt: str = Field(max_length=300)  # what the [[OWNER: …]] place asks for
    before: str = Field(default="", max_length=1500)  # the script text just before the place
    after: str = Field(default="", max_length=1500)  # and just after it
    claims: list[BriefClaim] = Field(default_factory=list, max_length=20)


class OwnerPartAgent(AgentTask):
    """A11's second job (owner request 2026-11-27): 3 options for one owner part — a fill-in with
    blanks for the owner's real details, a question to viewers, a neutral line from the brief. It never
    writes an experience as the owner's own; the pipeline checks that again in code."""

    code: ClassVar[str] = "A11_SCRIPTWRITING"
    prompt_name: ClassVar[str | None] = "A11_OWNER_PARTS"
    prompt_version: ClassVar[str | None] = "v1.0"
    task_type: ClassVar[str] = "script_draft"
    temperature: ClassVar[float] = 0.7
    max_output_tokens: ClassVar[int] = 1200
    input_model: ClassVar[type[BaseModel]] = OwnerPartInput

    def context(self, data: BaseModel, channel: Channel | None) -> dict[str, Any]:
        assert isinstance(data, OwnerPartInput)
        return {"channel_name": channel.name if channel else "", "language": data.language, "format": "LONG"}

    def user_message(self, data: BaseModel) -> str:
        assert isinstance(data, OwnerPartInput)
        return render_user(
            "Video title: {{ title | untrusted('title') }}\n"
            "The owner part asks for: {{ prompt | untrusted('owner_part_prompt') }}\n"
            "Script text just before the place: {{ before | untrusted('text_before') }}\n"
            "Script text just after the place: {{ after | untrusted('text_after') }}\n"
            "Brief claims (the only facts you may use): {{ claims | untrusted('brief_claims') }}",
            {
                "title": data.title,
                "prompt": data.prompt,
                "before": data.before or "(start of the part)",
                "after": data.after or "(end of the part)",
                "claims": json.dumps([c.model_dump() for c in data.claims], ensure_ascii=False),
            },
        )


A08 = IdeaGenerationAgent()
A09 = ResearchAgent()
A10 = FactCheckingAgent()
A11 = ScriptwritingAgent()
A11_PARTS = OwnerPartAgent()
CONTENT_AGENTS: dict[str, AgentTask] = {a.code: a for a in (A08, A09, A10, A11)}
