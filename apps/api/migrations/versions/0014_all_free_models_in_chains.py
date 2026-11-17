"""Every free model already registered goes into the default agent chains (owner request, 2026-11-17).

Before, a reasoning job tried 2 Gemini models, Groq 120b and the local model; a light job the two
Flash-Lite models, Groq 20b and the local model. Now each chain also tries the other free models
(best first, the local model last), so one model's bad answer or busy day does not stop the job.
Chains the owner has not changed (still exactly the 0011 default) are updated; edited chains are
left alone. Frozen copies, not imports, so this never changes.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-17
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOCAL = "ollama:qwen2.5:1.5b"
G38, G36 = "gemini:gemini-3.8-flash", "gemini:gemini-3.6-flash"
G35L, G31L = "gemini:gemini-3.5-flash-lite", "gemini:gemini-3.1-flash-lite"
Q120, Q20 = "groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b"
CHANGES: list[tuple[list[str], list[str]]] = [
    ([G38, G36, Q120, LOCAL], [G38, G36, Q120, G35L, G31L, Q20, LOCAL]),
    ([G35L, G31L, Q20, LOCAL], [G35L, G31L, Q20, G36, G38, Q120, LOCAL]),
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
