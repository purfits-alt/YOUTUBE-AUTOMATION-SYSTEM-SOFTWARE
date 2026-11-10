"""Move two enum CHECK constraints to the right column.

tools/gen_schema_sql.py attached ``-- enum X`` to the *first* text column of a line that declares
two (``label text, state text, -- enum voice_profile_state``). Databases created by 0002 before the
fix have the state check on ``voice_profiles.label`` and ``notification_deliveries.channel``.
This revision drops those and adds the checks on ``state``. On a database created after the fix it
changes nothing (the constraints are already right).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VOICE = "'RECORDING_SAMPLES','CONSENT_PENDING','VERIFYING','READY','DISABLED','REJECTED','DELETED'"
DELIVERY = "'CREATED','SUPPRESSED','DEFERRED','DIGEST_PENDING','QUEUED','SENT','RETRYING','FAILED','READ'"


def _move(table: str, wrong: str, values: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_{wrong}_check")
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_state_check")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {table}_state_check CHECK (state IN ({values}))")


def upgrade() -> None:
    _move("voice_profiles", "label", VOICE)
    _move("notification_deliveries", "channel", DELIVERY)


def downgrade() -> None:
    # The old placement was a bug; going back keeps the correct constraints.
    pass
