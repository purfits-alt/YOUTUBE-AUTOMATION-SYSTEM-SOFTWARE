# ruff: noqa: E501  (SQL text reads better unwrapped)
"""Every free model in every default agent chain, plus Gemma 4 (owner request, 2026-11-17).

The owner asked for all free models that are authentic, give real answers and keep TubeForge within
our rules and Google, YouTube and AdSense policies (FREE_TIER_PROVIDER_MATRIX §3.2, checked
2026-11-17 on the official pages):
- Gemma 4 on the Gemini API (`gemma-4-31b-it`, `gemma-4-26b-a4b-it`): "Free of charge", no paid
  tier; weights under Apache 2.0 (model card); Google claims no rights in outputs. Same Gemini
  terms and free-tier data use as the Gemini models already registered; same key.
- Not added: Groq `qwen/qwen3.8-27b` (a *preview* model, "for evaluation purposes only"), Mistral
  (free API access withdrawn), Cerebras (a trial needing a card), OpenRouter free models (providers
  may train on prompts; 50 requests/day), GitHub Models (prototyping only).

Chains: reasoning work tries the strong models first, light work the light ones; every chain ends
with the local model. Only chains still at the 0011 default change (owner edits are kept).
Frozen copies, not imports, so this never changes.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-17
"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NS = uuid.UUID("5d1e1c3a-6a0e-4a4b-9f3e-6c1b2e7d9a10")  # same namespace as 0007
LOCAL = "ollama:qwen2.5:1.5b"
G38, G36 = "gemini:gemini-3.8-flash", "gemini:gemini-3.6-flash"
G35L, G31L = "gemini:gemini-3.5-flash-lite", "gemini:gemini-3.1-flash-lite"
GM31, GM26 = "gemini:gemma-4-31b-it", "gemini:gemma-4-26b-a4b-it"
Q120, Q20 = "groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b"
GEMMA = [GM31, GM26]
CHANGES: list[tuple[list[str], list[str]]] = [
    ([G38, G36, Q120, LOCAL], [G38, G36, Q120, GM31, G35L, G31L, Q20, GM26, LOCAL]),
    ([G35L, G31L, Q20, LOCAL], [G35L, G31L, Q20, GM26, G36, G38, Q120, GM31, LOCAL]),
]


def _swap(old: list[str], new: list[str]) -> None:
    op.execute(
        sa.text(
            "UPDATE agent_configurations SET provider_chain = CAST(:new AS jsonb)"
            " WHERE provider_chain = CAST(:old AS jsonb)"
        ).bindparams(old=json.dumps(old), new=json.dumps(new))
    )


def upgrade() -> None:
    for code in GEMMA:
        op.execute(
            sa.text(
                "INSERT INTO provider_registry (code, capability, tier, enabled, paid_activation_step,"
                " licence, licence_url, lineage, commercial_use, data_use_training, languages, limits,"
                " verified_at, verified_url, notes)"
                " VALUES (:code, 'LLM', 'F', true, 0, 'Apache-2.0 (Gemma 4 weights); Gemini API Additional Terms',"
                " 'https://ai.google.dev/gemma/docs/core/model_card_4', 'Gemma 4 (Google DeepMind)', 'YES', true,"
                " ARRAY['en','es','fr','de','ur'], CAST(:limits AS jsonb), DATE '2026-11-17',"
                " 'https://aistudio.google.com/docs/pricing',"
                " 'Free of charge, no paid tier. Free tier: content used to improve Google products. Uses the Gemini key.')"
                " ON CONFLICT (code) DO NOTHING"
            ).bindparams(code=code, limits='{"rpd": 200, "tpd": 500000, "placeholder": true}')
        )
        for metric, value in (("REQUESTS", 200), ("TOKENS", 500_000)):
            op.execute(
                sa.text(
                    "INSERT INTO usage_limits (id, provider_code, scope, scope_ref, metric, period,"
                    " limit_value, reset_tz) VALUES (:id, :code, 'GLOBAL', NULL, :metric, 'DAY', :value,"
                    " 'America/Los_Angeles') ON CONFLICT DO NOTHING"
                ).bindparams(id=uuid.uuid5(NS, f"{code}:{metric}"), code=code, metric=metric, value=value)
            )
    for old, new in CHANGES:
        _swap(old, new)


def downgrade() -> None:
    for old, new in CHANGES:
        _swap(new, old)
    for table, column in (
        ("provider_reverify_reminders", "provider_code"),
        ("usage_limits", "provider_code"),
        ("provider_credentials", "provider_code"),
        ("provider_registry", "code"),
    ):
        stmt = sa.text(f"DELETE FROM {table} WHERE {column} IN :codes")  # noqa: S608 - fixed names
        op.execute(stmt.bindparams(sa.bindparam("codes", value=GEMMA, expanding=True)))
