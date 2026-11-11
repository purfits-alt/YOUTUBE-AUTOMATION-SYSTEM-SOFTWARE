"""A02 Niche Discovery, A03 Trend Intelligence, A05 Keyword Research, A06 Channel Strategy and
A07 Channel Branding (AGENT_PROMPTS v1.0, CHANNEL_DISCOVERY_SPEC).

Every document, owner note and article title reaches the model only through the ``untrusted``
filter. Numbers (pageview metrics, signal strengths) are computed in code and passed in; the
pipelines in ``tubeforge_agents.discovery`` check and score the answers.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

from tubeforge.db.models import Channel
from tubeforge.research.blueprint import LICENSED_FONTS
from tubeforge_agents.base import AgentTask
from tubeforge_agents.prompting import render_user

Language = Literal["en", "es", "fr", "de", "ur"]
HARDWARE_PROFILE = "H-LITE"


class DocIn(BaseModel):
    id: str
    url: str
    title: str | None = None
    text: str = Field(max_length=4000)


DOCS = """{% for d in documents %}{{ d.text | untrusted(d.id, d.url) }}
{% endfor %}"""


class NicheInput(BaseModel):
    languages: list[Language] = Field(min_length=1, max_length=5)
    interests: list[str] = Field(default_factory=list, max_length=10)
    avoid: list[str] = Field(default_factory=list, max_length=20)
    hardware_profile: str = HARDWARE_PROFILE
    documents: list[DocIn] = Field(min_length=1, max_length=40)
    metrics: list[dict[str, Any]] = Field(default_factory=list, max_length=40)


class NicheDiscoveryAgent(AgentTask):
    code: ClassVar[str] = "A02_NICHE_DISCOVERY"
    task_type: ClassVar[str] = "research"
    temperature: ClassVar[float] = 0.2
    max_output_tokens: ClassVar[int] = 6000
    input_model: ClassVar[type[BaseModel]] = NicheInput

    def context(self, data: BaseModel, channel: Channel | None) -> dict[str, Any]:
        assert isinstance(data, NicheInput)
        return {"language": data.languages[0], "hardware_profile": data.hardware_profile}

    def user_message(self, data: BaseModel) -> str:
        assert isinstance(data, NicheInput)
        return render_user(
            "Languages: {{ languages | join(', ') }}. Hardware profile: {{ hw }}.\n"
            "Owner interests (empty = let TubeForge suggest): "
            "{{ interests | untrusted('owner_interests') }}\n"
            "Niches to avoid: {{ avoid | untrusted('owner_avoid') }}\n"
            "Pageview metrics computed in code (document_id refers to the documents below):\n"
            "{{ metrics | untrusted('metrics') }}\n"
            "Source documents:\n" + DOCS,
            {
                "languages": data.languages,
                "hw": data.hardware_profile,
                "interests": json.dumps(data.interests, ensure_ascii=False),
                "avoid": json.dumps(data.avoid, ensure_ascii=False),
                "metrics": json.dumps(data.metrics, ensure_ascii=False),
                "documents": [d.model_dump() for d in data.documents],
            },
        )


class TrendSignal(BaseModel):
    term: str = Field(max_length=120)
    pillar: str = Field(max_length=60)
    signal_strength: float
    kind: Literal["pageviews", "feeds"]
    document_ids: list[str] = Field(max_length=10)


class TrendInput(BaseModel):
    language: Language = "en"
    pillars: list[str] = Field(min_length=1, max_length=7)
    signals: list[TrendSignal] = Field(max_length=30)
    documents: list[DocIn] = Field(max_length=30)


class TrendIntelligenceAgent(AgentTask):
    code: ClassVar[str] = "A03_TREND_INTELLIGENCE"
    task_type: ClassVar[str] = "research"
    max_output_tokens: ClassVar[int] = 2500
    input_model: ClassVar[type[BaseModel]] = TrendInput

    def context(self, data: BaseModel, channel: Channel | None) -> dict[str, Any]:
        assert isinstance(data, TrendInput)
        return {
            "channel_name": channel.name if channel else "",
            "language": data.language,
            "pillars": json.dumps(data.pillars, ensure_ascii=False),
        }

    def user_message(self, data: BaseModel) -> str:
        assert isinstance(data, TrendInput)
        return render_user(
            "Signals computed in code:\n{{ signals | untrusted('signals') }}\nSource documents:\n" + DOCS,
            {
                "signals": json.dumps([s.model_dump() for s in data.signals], ensure_ascii=False),
                "documents": [d.model_dump() for d in data.documents],
            },
        )


class KeywordInput(BaseModel):
    language: Language = "en"
    seeds: list[str] = Field(min_length=1, max_length=10)
    documents: list[DocIn] = Field(default_factory=list, max_length=10)


class KeywordResearchAgent(AgentTask):
    code: ClassVar[str] = "A05_KEYWORD_RESEARCH"
    task_type: ClassVar[str] = "seo"
    max_output_tokens: ClassVar[int] = 3000
    input_model: ClassVar[type[BaseModel]] = KeywordInput

    def context(self, data: BaseModel, channel: Channel | None) -> dict[str, Any]:
        assert isinstance(data, KeywordInput)
        return {"channel_name": channel.name if channel else "", "language": data.language}

    def user_message(self, data: BaseModel) -> str:
        assert isinstance(data, KeywordInput)
        return render_user(
            "Seeds: {{ seeds | untrusted('seeds') }}\nSource documents:\n" + DOCS,
            {
                "seeds": json.dumps(data.seeds, ensure_ascii=False),
                "documents": [d.model_dump() for d in data.documents],
            },
        )


class NicheBrief(BaseModel):
    name: str = Field(max_length=80)
    summary: str = Field(max_length=600)
    language: Language
    originality_angles: list[str] = Field(default_factory=list, max_length=5)


class StrategyInput(BaseModel):
    niche: NicheBrief
    owner_notes: str = Field(default="", max_length=2000)
    hardware_profile: str = HARDWARE_PROFILE


class ChannelStrategyAgent(AgentTask):
    code: ClassVar[str] = "A06_CHANNEL_STRATEGY"
    task_type: ClassVar[str] = "ideas"
    temperature: ClassVar[float] = 0.5
    max_output_tokens: ClassVar[int] = 12000
    input_model: ClassVar[type[BaseModel]] = StrategyInput

    def context(self, data: BaseModel, channel: Channel | None) -> dict[str, Any]:
        assert isinstance(data, StrategyInput)
        return {"language": data.niche.language, "hardware_profile": data.hardware_profile}

    def user_message(self, data: BaseModel) -> str:
        assert isinstance(data, StrategyInput)
        return render_user(
            "Shortlisted niche:\n{{ niche | untrusted('niche') }}\n"
            "Owner notes:\n{{ notes | untrusted('owner_notes') }}",
            {"niche": data.niche.model_dump_json(), "notes": data.owner_notes or "(none)"},
        )


class BrandingInput(BaseModel):
    niche: NicheBrief


class ChannelBrandingAgent(AgentTask):
    code: ClassVar[str] = "A07_CHANNEL_BRANDING"
    task_type: ClassVar[str] = "default"
    temperature: ClassVar[float] = 0.7
    max_output_tokens: ClassVar[int] = 2500
    input_model: ClassVar[type[BaseModel]] = BrandingInput

    def context(self, data: BaseModel, channel: Channel | None) -> dict[str, Any]:
        assert isinstance(data, BrandingInput)
        return {"language": data.niche.language, "licensed_fonts": ", ".join(LICENSED_FONTS)}

    def user_message(self, data: BaseModel) -> str:
        assert isinstance(data, BrandingInput)
        return render_user(
            "Niche:\n{{ niche | untrusted('niche') }}", {"niche": data.niche.model_dump_json()}
        )


A02 = NicheDiscoveryAgent()
A03 = TrendIntelligenceAgent()
A05 = KeywordResearchAgent()
A06 = ChannelStrategyAgent()
A07 = ChannelBrandingAgent()
DISCOVERY_AGENTS: dict[str, AgentTask] = {a.code: a for a in (A02, A03, A05, A06, A07)}
