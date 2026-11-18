"""Live pipeline progress (owner request 2026-11-18, ADR-0031).

``job_progress``: one row per queued or running job, with a percentage and a stage in plain words, so
the Pipeline page and Script Studio show what is being worked on, how far it is and what comes next.
Added only where missing: databases built after this change already get it from schema_v1.sql (0002).

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS job_progress (
          id uuid PRIMARY KEY,
          kind text NOT NULL,
          entity_type text NOT NULL CHECK (entity_type IN
            ('video_project','channel','niche_report','niche_candidate','script_version')),
          entity_id uuid NOT NULL,
          project_id uuid NULL,
          status text NOT NULL CHECK (status IN ('QUEUED','RUNNING','DONE','FAILED','WAITING')),
          pct smallint NOT NULL DEFAULT 0 CHECK (pct BETWEEN 0 AND 100),
          stage text NOT NULL,
          message text NULL,
          queued_at timestamptz NOT NULL DEFAULT now(),
          started_at timestamptz NULL,
          updated_at timestamptz NOT NULL DEFAULT now(),
          finished_at timestamptz NULL
        )
        """
    )
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'job_progress_updated_at') THEN "
        "CREATE TRIGGER job_progress_updated_at BEFORE UPDATE ON job_progress FOR EACH ROW "
        "EXECUTE FUNCTION tf_set_updated_at(); END IF; END $$"
    )
    for name, cols in (
        ("entity_id_queued_at", "entity_id, queued_at DESC"),
        ("project_id_queued_at", "project_id, queued_at DESC"),
        ("status_updated_at", "status, updated_at DESC"),
    ):
        op.execute(f"CREATE INDEX IF NOT EXISTS job_progress_{name}_idx ON job_progress ({cols})")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS job_progress")
