"""Add a second free Gemini model to the default agent chains.

Each Gemini model has its own capacity. When ``gemini-3.8-flash`` answered 503 ("overloaded")
three times, discovery failed although ``gemini-3.6-flash`` on the same free key was available.
Chains the owner has not changed (still exactly the 0008 default) get the second model after the
first; chains the owner edited are left alone. Frozen copies, not imports, so this never changes.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-12
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOCAL = "ollama:qwen2.5:1.5b"
CHANGES: list[tuple[list[str], list[str]]] = [
    (
        ["gemini:gemini-3.8-flash", "groq:openai/gpt-oss-120b", LOCAL],
        ["gemini:gemini-3.8-flash", "gemini:gemini-3.6-flash", "groq:openai/gpt-oss-120b", LOCAL],
    ),
    (
        ["gemini:gemini-3.5-flash-lite", "groq:openai/gpt-oss-20b", LOCAL],
        ["gemini:gemini-3.5-flash-lite", "gemini:gemini-3.1-flash-lite", "groq:openai/gpt-oss-20b", LOCAL],
    ),
]


def _swap(old: list[str], new: list[str]) -> None:
    op.execute(
        sa.text(
            "UPDATE agent_configurations SET provider_chain = CAST(:new AS jsonb)"
            " WHERE provider_chain = CAST(:old AS jsonb)"
        ).bindparams(old=json.dumps(old), new=json.dumps(new))
    )


def upgrade() -> None:
    for old, new in CHANGES:
        _swap(old, new)


def downgrade() -> None:
    for old, new in CHANGES:
        _swap(new, old)
