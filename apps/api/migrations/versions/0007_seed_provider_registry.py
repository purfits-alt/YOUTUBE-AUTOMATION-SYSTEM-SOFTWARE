"""Seed the provider registry (LLM providers) and placeholder free-tier limits.

From FREE_TIER_PROVIDER_MATRIX §3.2, re-checked 2026-11-09 on the official pages:
- Gemini API free tier: the "Free of charge" Standard-tier models (gemini-3.8-flash, 3.6-flash,
  3.5-flash-lite, 3.1-flash-lite). The free tier may use content to improve Google's products.
  gemini-2.5-flash is deprecated (routes to 3.5-flash-lite from 2026-12-01) and is not seeded.
- Groq free plan: openai/gpt-oss-120b and openai/gpt-oss-20b (Apache-2.0 weights).
- Ollama (local): qwen2.5:1.5b — Qwen2.5-1.5B-Instruct is Apache-2.0 (the 3B model is
  qwen-research, so it is NOT used).
- One Tier P row (gemini-3.1-pro-preview, not on the free tier) ships disabled at step 0 so the
  two-step activation rule is visible and tested.

Placeholder limits (COST_CONTROL_SPEC §2, until the owner enters the console values):
Gemini 200 requests / 500k tokens per day; Groq 500 requests / 150k tokens per day (per model).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-09
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NS = uuid.UUID("5d1e1c3a-6a0e-4a4b-9f3e-6c1b2e7d9a10")
GEMINI_TERMS = "https://ai.google.dev/gemini-api/terms"
GEMINI_PRICING = "https://ai.google.dev/gemini-api/docs/pricing"
GROQ_MODELS = "https://console.groq.com/docs/models"
QWEN_CARD = "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct"

# code, tier, enabled, licence, licence_url, commercial, data_use_training, limits, verified_url, notes
ROWS: list[tuple[str, str, bool, str, str, str, bool | None, str, str, str]] = [
    *[
        (
            f"gemini:{m}",
            "F",
            True,
            "Gemini API Additional Terms of Service",
            GEMINI_TERMS,
            "YES",
            True,
            '{"rpd": 200, "tpd": 500000, "placeholder": true}',
            GEMINI_PRICING,
            "Free tier: 'content used to improve our products'. Key from a Cloud project with NO billing.",
        )
        for m in ("gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
    ],
    (
        "gemini:gemini-3.1-pro-preview",
        "P",
        False,
        "Gemini API Additional Terms of Service (paid tier)",
        GEMINI_TERMS,
        "YES",
        False,
        "{}",
        GEMINI_PRICING,
        "Not on the free tier. Paid: needs the two-step owner activation and a monthly cap.",
    ),
    *[
        (
            f"groq:openai/{m}",
            "F",
            True,
            "Groq Services Agreement; model weights Apache-2.0",
            GROQ_MODELS,
            "YES",
            None,
            '{"rpd": 500, "tpd": 150000, "placeholder": true}',
            GROQ_MODELS,
            "Free-plan limits are shown only in the Groq console; the owner enters them.",
        )
        for m in ("gpt-oss-120b", "gpt-oss-20b")
    ],
    (
        "ollama:qwen2.5:1.5b",
        "L",
        True,
        "Apache-2.0",
        QWEN_CARD,
        "YES",
        False,
        "{}",
        QWEN_CARD,
        "Runs on this PC (Ollama, MIT). Install with: ollama pull qwen2.5:1.5b (about 1 GB).",
    ),
]
LIMITS = {"gemini": (200, 500_000), "groq": (500, 150_000)}


def upgrade() -> None:
    for code, tier, enabled, lic, lic_url, commercial, data_use, limits, url, notes in ROWS:
        op.execute(
            sa.text(
                "INSERT INTO provider_registry (code, capability, tier, enabled, paid_activation_step,"
                " licence, licence_url, commercial_use, data_use_training, languages, limits,"
                " verified_at, verified_url, notes)"
                " VALUES (:code, 'LLM', :tier, :enabled, 0, :lic, :lic_url, :commercial, :data_use,"
                " ARRAY['en','es','fr','de','ur'], CAST(:limits AS jsonb), DATE '2026-11-09', :url, :notes)"
            ).bindparams(
                code=code,
                tier=tier,
                enabled=enabled,
                lic=lic,
                lic_url=lic_url,
                commercial=commercial,
                data_use=data_use,
                limits=limits,
                url=url,
                notes=notes,
            )
        )
        family = code.split(":", 1)[0]
        if tier == "F" and family in LIMITS:
            for metric, value in zip(("REQUESTS", "TOKENS"), LIMITS[family], strict=True):
                op.execute(
                    sa.text(
                        "INSERT INTO usage_limits (id, provider_code, scope, scope_ref, metric, period,"
                        " limit_value, reset_tz) VALUES (:id, :code, 'GLOBAL', NULL, :metric, 'DAY', :value,"
                        " 'America/Los_Angeles')"
                    ).bindparams(id=uuid.uuid5(NS, f"{code}:{metric}"), code=code, metric=metric, value=value)
                )


def downgrade() -> None:
    codes = [r[0] for r in ROWS]
    for table, column in (
        ("usage_limits", "provider_code"),
        ("provider_credentials", "provider_code"),
        ("provider_registry", "code"),
    ):
        stmt = sa.text(f"DELETE FROM {table} WHERE {column} IN :codes")  # noqa: S608 - fixed names
        op.execute(stmt.bindparams(sa.bindparam("codes", value=codes, expanding=True)))
