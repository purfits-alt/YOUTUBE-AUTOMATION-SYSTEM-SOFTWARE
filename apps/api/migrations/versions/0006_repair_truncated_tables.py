"""Rebuild two tables that the schema generator cut short.

tools/gen_schema_sql.py ended a table at the first ``);`` — also inside a comment — and mis-split a
column list on quotes inside comments. Databases built from the affected schema_v1.sql have:

- ``provider_credentials`` with **no columns** (header comment ``-- API keys (owner's own); …``)
- ``seo_packages`` without its last 13 columns (schema_v1.sql regenerated in Phase 4)

Neither table held data yet (used from Phase 5 / Phase 10), so each is dropped and recreated, but
only where its key column is missing. On a database built after the fix this changes nothing.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROVIDER_CREDENTIALS = """
CREATE TABLE provider_credentials (
  provider_code text PRIMARY KEY,
  secret_enc bytea NOT NULL,
  key_id text NOT NULL,
  label text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER provider_credentials_updated_at BEFORE UPDATE ON provider_credentials
  FOR EACH ROW EXECUTE FUNCTION tf_set_updated_at();
ALTER TABLE provider_credentials ADD FOREIGN KEY (provider_code) REFERENCES provider_registry;
"""

SEO_PACKAGES = """
CREATE TABLE seo_packages (
  id uuid PRIMARY KEY,
  project_id uuid NOT NULL,
  channel_id uuid NOT NULL,
  version int NOT NULL,
  title_options jsonb NOT NULL,
  selected_title text NULL CHECK (char_length(selected_title) <= 100 AND selected_title !~ '[<>]'),
  description text NOT NULL CHECK (octet_length(description) <= 5000),
  tags text[] NOT NULL DEFAULT '{}',
  hashtags text[] NOT NULL DEFAULT '{}',
  chapters jsonb NOT NULL DEFAULT '[]',
  playlist_suggestions jsonb NOT NULL DEFAULT '[]',
  category_id text NULL,
  default_language text NOT NULL,
  default_audio_language text NOT NULL,
  made_for_kids boolean NULL,
  made_for_kids_decided_by uuid NULL,
  made_for_kids_decided_at timestamptz NULL,
  misleading_check jsonb NULL,
  content_sha256 char(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, version)
);
ALTER TABLE seo_packages ADD FOREIGN KEY (project_id) REFERENCES video_projects;
"""


def _has_column(table: str, column: str) -> bool:
    found = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        )
        .first()
    )
    return found is not None


def upgrade() -> None:
    for table, key, ddl in (
        ("provider_credentials", "provider_code", PROVIDER_CREDENTIALS),
        ("seo_packages", "content_sha256", SEO_PACKAGES),
    ):
        if not _has_column(table, key):
            op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            op.execute(ddl)


def downgrade() -> None:
    # Going back to a broken table is never useful; the correct tables stay.
    pass
