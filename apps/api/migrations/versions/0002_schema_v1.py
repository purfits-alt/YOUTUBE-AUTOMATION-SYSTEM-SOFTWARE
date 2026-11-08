"""Application schema v1: every table of DATABASE_SCHEMA §1–§12.

The DDL is generated from the approved document by tools/gen_schema_sql.py and stored in
tubeforge/db/schema_v1.sql (CI checks it is up to date). This revision applies that frozen file.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-08
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "tubeforge" / "db" / "schema_v1.sql"

# Every application table (not Procrastinate's), dropped together with their triggers and FKs.
DROP_APP_TABLES = """
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables
           WHERE schemaname = 'public' AND tablename NOT LIKE 'procrastinate%'
             AND tablename <> 'alembic_version' LOOP
    EXECUTE format('DROP TABLE IF EXISTS public.%I CASCADE', r.tablename);
  END LOOP;
END $$;
DROP FUNCTION IF EXISTS tf_set_updated_at() CASCADE;
DROP FUNCTION IF EXISTS tf_append_only() CASCADE;
"""


def _run_raw(sql: str) -> None:
    op.get_bind().exec_driver_sql(sql.replace("%", "%%"))


def upgrade() -> None:
    _run_raw(SCHEMA_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    _run_raw(DROP_APP_TABLES)
