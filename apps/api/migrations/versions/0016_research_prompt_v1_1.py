"""A09 Research prompt v1.1 (owner report 2026-11-27).

Research for "How Late Meals Impact Deep Sleep and Recovery" stopped at 50 %: A09 refused because the
articles covered sleep, heart rate variability and digestion but not the exact link in the title.
v1.1 writes the brief from what the sources do say and lists the missing link as an open question;
it refuses only when fewer than 2 documents are about any core part of the idea.

Only installs still on the seeded v1.0 move; a version the owner changed stays.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: agent code → (old prompt version, new prompt version)
PROMPTS: dict[str, tuple[str, str]] = {"A09_RESEARCH": ("v1.0", "v1.1")}

_SET = (
    "UPDATE agent_configurations SET prompt_version = :new WHERE agent_code = :code AND prompt_version = :old"
)


def upgrade() -> None:
    for code, (old, new) in PROMPTS.items():
        op.execute(sa.text(_SET).bindparams(code=code, old=old, new=new))


def downgrade() -> None:
    for code, (old, new) in PROMPTS.items():
        op.execute(sa.text(_SET).bindparams(code=code, old=new, new=old))
