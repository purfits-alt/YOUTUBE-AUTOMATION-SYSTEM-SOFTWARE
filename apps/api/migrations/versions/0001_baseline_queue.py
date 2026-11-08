"""Baseline: Procrastinate job-queue schema (ADR-0004).

Application tables (DATABASE_SCHEMA §1–§12) are added from Phase 3 onwards.

Revision ID: 0001
Revises:
Create Date: 2026-11-08
"""

from collections.abc import Sequence

from alembic import op
from procrastinate.schema import SchemaManager

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Drops every object the Procrastinate schema created (tables, functions, types).
DROP_PROCRASTINATE = """
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables
           WHERE schemaname = 'public' AND tablename LIKE 'procrastinate%' LOOP
    EXECUTE format('DROP TABLE IF EXISTS public.%I CASCADE', r.tablename);
  END LOOP;
  FOR r IN SELECT p.oid::regprocedure AS sig FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
           WHERE n.nspname = 'public' AND p.proname LIKE 'procrastinate%' LOOP
    EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
  END LOOP;
  FOR r IN SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
           WHERE n.nspname = 'public' AND t.typname LIKE 'procrastinate%' AND t.typtype IN ('e', 'c') LOOP
    EXECUTE format('DROP TYPE IF EXISTS public.%I CASCADE', r.typname);
  END LOOP;
END $$;
"""


def _run_raw(sql: str) -> None:
    # exec_driver_sql avoids SQLAlchemy ':name' parsing; '%' is doubled because psycopg
    # still treats it as a placeholder marker when executed through the driver.
    op.get_bind().exec_driver_sql(sql.replace("%", "%%"))


def upgrade() -> None:
    _run_raw(SchemaManager.get_schema())


def downgrade() -> None:
    _run_raw(DROP_PROCRASTINATE)
