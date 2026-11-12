"""The 32 agents of AI_AGENT_ARCHITECTURE §2 (+ the HELLO test agent) and their default settings.

Migration 0008 seeds ``agent_configurations`` from a frozen copy of this table and 0011 adds a
second Gemini model to the default chains; a unit test keeps the result equal to this table.
The owner changes chains and limits later in the Agent Control Center.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Kind = Literal["LLM", "HYBRID", "DETERMINISTIC", "ADAPTER", "TEST"]
LOCAL = "ollama:qwen2.5:1.5b"
# A second free Gemini model before Groq: each model has its own capacity (migration 0011).
REASONING = ["gemini:gemini-3.8-flash", "gemini:gemini-3.6-flash", "groq:openai/gpt-oss-120b", LOCAL]
LIGHT = ["gemini:gemini-3.5-flash-lite", "gemini:gemini-3.1-flash-lite", "groq:openai/gpt-oss-20b", LOCAL]


@dataclass(frozen=True)
class AgentInfo:
    code: str
    name: str
    kind: Kind
    auditor: bool = False
    chain: list[str] = field(default_factory=list)
    prompt_version: str = "none"
    limits: dict[str, Any] = field(default_factory=lambda: {"max_runtime_s": 600})


def _llm(
    code: str,
    name: str,
    chain: list[str],
    calls: int = 30,
    prompt: str = "v1.0",
    kind: Kind = "LLM",
    auditor: bool = False,
) -> AgentInfo:
    return AgentInfo(
        code,
        name,
        kind,
        auditor,
        chain,
        prompt,
        {"calls_per_day": calls, "tokens_per_day": 300_000, "max_runtime_s": 300},
    )


AGENTS: list[AgentInfo] = [
    AgentInfo("A01_ORCHESTRATOR", "Master YouTube Orchestrator", "DETERMINISTIC"),
    _llm("A02_NICHE_DISCOVERY", "Niche Discovery", REASONING),
    _llm("A03_TREND_INTELLIGENCE", "Trend Intelligence", LIGHT, kind="HYBRID"),
    AgentInfo("A04_COMPETITOR_RESEARCH", "Competitor Research", "DETERMINISTIC"),
    _llm("A05_KEYWORD_RESEARCH", "Keyword Research", LIGHT),
    _llm("A06_CHANNEL_STRATEGY", "Channel Strategy", REASONING),
    _llm("A07_CHANNEL_BRANDING", "Channel Branding", REASONING),
    _llm("A08_IDEA_GENERATION", "Idea Generation", REASONING, prompt="v1.1"),
    _llm("A09_RESEARCH", "Research", REASONING, calls=40),
    _llm("A10_FACT_CHECKING", "Fact-Checking", REASONING),
    _llm("A11_SCRIPTWRITING", "Scriptwriting", REASONING, prompt="v1.1"),
    _llm("A12_STORYBOARD", "Storyboard", REASONING, prompt="v1.1"),
    _llm("A13_VISUAL_CREATIVE", "Visual Creative", LIGHT, kind="HYBRID"),
    AgentInfo("A14_AI_IMAGE", "AI Image Generation", "ADAPTER"),
    AgentInfo("A15_VOICEOVER", "Voiceover", "HYBRID"),
    AgentInfo("A16_VIDEO_PRODUCTION", "Video Production", "DETERMINISTIC"),
    _llm("A17_VIDEO_EDITING", "Video Editing", LIGHT, kind="HYBRID"),
    _llm("A18_THUMBNAIL_DESIGN", "Thumbnail Design", REASONING, prompt="v1.1", kind="HYBRID"),
    _llm("A19_YOUTUBE_SEO", "YouTube SEO", LIGHT, calls=20),
    AgentInfo("A20_CAPTIONS", "Caption & Subtitle", "DETERMINISTIC"),
    AgentInfo("A21_COPYRIGHT_AUDITOR", "Copyright Auditor", "DETERMINISTIC", auditor=True),
    _llm("A22_POLICY_AUDITOR", "YouTube Policy Auditor", LIGHT, prompt="v1.1", kind="HYBRID", auditor=True),
    AgentInfo("A23_QUALITY_AUDITOR", "Video Quality Auditor", "DETERMINISTIC", auditor=True),
    AgentInfo("A24_UPLOAD", "Upload", "DETERMINISTIC"),
    AgentInfo("A25_PUBLISHING", "Publishing & Scheduling", "DETERMINISTIC"),
    AgentInfo("A26_ANALYTICS", "Analytics", "DETERMINISTIC"),
    _llm("A27_GROWTH", "Growth Optimization", REASONING),
    _llm("A28_COMMENT_MODERATION", "Comment Moderation", LIGHT),
    AgentInfo("A29_NOTIFICATION", "Notification", "DETERMINISTIC"),
    AgentInfo("A30_SECURITY_AUDITOR", "Security Auditor", "DETERMINISTIC", auditor=True),
    AgentInfo("A31_SYSTEM_AUDITOR", "System Auditor", "DETERMINISTIC", auditor=True),
    AgentInfo("A32_COST_MONITOR", "Free-Tier Cost & Usage Monitor", "DETERMINISTIC", auditor=True),
    AgentInfo(
        "T00_HELLO",
        "Hello test agent",
        "TEST",
        chain=LIGHT,
        prompt_version="v1.0",
        limits={"calls_per_day": 20, "tokens_per_day": 20_000, "max_runtime_s": 60},
    ),
]
BY_CODE = {a.code: a for a in AGENTS}
