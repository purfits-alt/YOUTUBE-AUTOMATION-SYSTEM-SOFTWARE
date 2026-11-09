"""Seed agent_configurations: the 32 agents of AI_AGENT_ARCHITECTURE §2 and the HELLO test agent.

Frozen copy of workers/tubeforge_agents/catalogue.py at this revision (a unit test compares them).
Chains: REASONING = gemini-3.8-flash → groq gpt-oss-120b → local qwen2.5:1.5b; LIGHT = gemini-3.5-
flash-lite → groq gpt-oss-20b → local. Per-day call budgets follow COST_CONTROL_SPEC §2.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-09
"""

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# code, name, is_auditor, prompt_version, provider_chain, limits
AGENTS: list[tuple[str, str, bool, str, list[str], dict[str, Any]]] = [
    ("A01_ORCHESTRATOR", "Master YouTube Orchestrator", False, "none", [], {"max_runtime_s": 600}),
    (
        "A02_NICHE_DISCOVERY",
        "Niche Discovery",
        False,
        "v1.0",
        ["gemini:gemini-3.8-flash", "groq:openai/gpt-oss-120b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 30, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    (
        "A03_TREND_INTELLIGENCE",
        "Trend Intelligence",
        False,
        "v1.0",
        ["gemini:gemini-3.5-flash-lite", "groq:openai/gpt-oss-20b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 30, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    ("A04_COMPETITOR_RESEARCH", "Competitor Research", False, "none", [], {"max_runtime_s": 600}),
    (
        "A05_KEYWORD_RESEARCH",
        "Keyword Research",
        False,
        "v1.0",
        ["gemini:gemini-3.5-flash-lite", "groq:openai/gpt-oss-20b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 30, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    (
        "A06_CHANNEL_STRATEGY",
        "Channel Strategy",
        False,
        "v1.0",
        ["gemini:gemini-3.8-flash", "groq:openai/gpt-oss-120b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 30, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    (
        "A07_CHANNEL_BRANDING",
        "Channel Branding",
        False,
        "v1.0",
        ["gemini:gemini-3.8-flash", "groq:openai/gpt-oss-120b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 30, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    (
        "A08_IDEA_GENERATION",
        "Idea Generation",
        False,
        "v1.1",
        ["gemini:gemini-3.8-flash", "groq:openai/gpt-oss-120b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 30, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    (
        "A09_RESEARCH",
        "Research",
        False,
        "v1.0",
        ["gemini:gemini-3.8-flash", "groq:openai/gpt-oss-120b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 40, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    (
        "A10_FACT_CHECKING",
        "Fact-Checking",
        False,
        "v1.0",
        ["gemini:gemini-3.8-flash", "groq:openai/gpt-oss-120b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 30, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    (
        "A11_SCRIPTWRITING",
        "Scriptwriting",
        False,
        "v1.1",
        ["gemini:gemini-3.8-flash", "groq:openai/gpt-oss-120b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 30, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    (
        "A12_STORYBOARD",
        "Storyboard",
        False,
        "v1.1",
        ["gemini:gemini-3.8-flash", "groq:openai/gpt-oss-120b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 30, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    (
        "A13_VISUAL_CREATIVE",
        "Visual Creative",
        False,
        "v1.0",
        ["gemini:gemini-3.5-flash-lite", "groq:openai/gpt-oss-20b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 30, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    ("A14_AI_IMAGE", "AI Image Generation", False, "none", [], {"max_runtime_s": 600}),
    ("A15_VOICEOVER", "Voiceover", False, "none", [], {"max_runtime_s": 600}),
    ("A16_VIDEO_PRODUCTION", "Video Production", False, "none", [], {"max_runtime_s": 600}),
    (
        "A17_VIDEO_EDITING",
        "Video Editing",
        False,
        "v1.0",
        ["gemini:gemini-3.5-flash-lite", "groq:openai/gpt-oss-20b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 30, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    (
        "A18_THUMBNAIL_DESIGN",
        "Thumbnail Design",
        False,
        "v1.1",
        ["gemini:gemini-3.8-flash", "groq:openai/gpt-oss-120b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 30, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    (
        "A19_YOUTUBE_SEO",
        "YouTube SEO",
        False,
        "v1.0",
        ["gemini:gemini-3.5-flash-lite", "groq:openai/gpt-oss-20b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 20, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    ("A20_CAPTIONS", "Caption & Subtitle", False, "none", [], {"max_runtime_s": 600}),
    ("A21_COPYRIGHT_AUDITOR", "Copyright Auditor", True, "none", [], {"max_runtime_s": 600}),
    (
        "A22_POLICY_AUDITOR",
        "YouTube Policy Auditor",
        True,
        "v1.1",
        ["gemini:gemini-3.5-flash-lite", "groq:openai/gpt-oss-20b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 30, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    ("A23_QUALITY_AUDITOR", "Video Quality Auditor", True, "none", [], {"max_runtime_s": 600}),
    ("A24_UPLOAD", "Upload", False, "none", [], {"max_runtime_s": 600}),
    ("A25_PUBLISHING", "Publishing & Scheduling", False, "none", [], {"max_runtime_s": 600}),
    ("A26_ANALYTICS", "Analytics", False, "none", [], {"max_runtime_s": 600}),
    (
        "A27_GROWTH",
        "Growth Optimization",
        False,
        "v1.0",
        ["gemini:gemini-3.8-flash", "groq:openai/gpt-oss-120b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 30, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    (
        "A28_COMMENT_MODERATION",
        "Comment Moderation",
        False,
        "v1.0",
        ["gemini:gemini-3.5-flash-lite", "groq:openai/gpt-oss-20b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 30, "tokens_per_day": 300000, "max_runtime_s": 300},
    ),
    ("A29_NOTIFICATION", "Notification", False, "none", [], {"max_runtime_s": 600}),
    ("A30_SECURITY_AUDITOR", "Security Auditor", True, "none", [], {"max_runtime_s": 600}),
    ("A31_SYSTEM_AUDITOR", "System Auditor", True, "none", [], {"max_runtime_s": 600}),
    ("A32_COST_MONITOR", "Free-Tier Cost & Usage Monitor", True, "none", [], {"max_runtime_s": 600}),
    (
        "T00_HELLO",
        "Hello test agent",
        False,
        "v1.0",
        ["gemini:gemini-3.5-flash-lite", "groq:openai/gpt-oss-20b", "ollama:qwen2.5:1.5b"],
        {"calls_per_day": 20, "tokens_per_day": 20000, "max_runtime_s": 60},
    ),
]


def upgrade() -> None:
    for code, name, auditor, prompt, chain, limits in AGENTS:
        op.execute(
            sa.text(
                "INSERT INTO agent_configurations (agent_code, name, version, is_auditor, enabled,"
                " prompt_version, provider_chain, limits, permissions) VALUES (:code, :name, '1.0.0',"
                " :auditor, true, :prompt, CAST(:chain AS jsonb), CAST(:limits AS jsonb), '{}'::jsonb)"
            ).bindparams(
                code=code,
                name=name,
                auditor=auditor,
                prompt=prompt,
                chain=json.dumps(chain),
                limits=json.dumps(limits),
            )
        )


def downgrade() -> None:
    op.execute("DELETE FROM agent_runs")
    op.execute("DELETE FROM agent_configurations")
