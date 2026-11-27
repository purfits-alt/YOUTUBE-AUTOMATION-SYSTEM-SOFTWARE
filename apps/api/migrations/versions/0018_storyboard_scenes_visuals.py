"""Phase 8 step B: storyboard and scene visuals.

- ``storyboards.script_version_id`` (the locked script it was cut from) and ``author_type``.
- ``scenes``: ``is_hook``, ``pattern_interrupt``, the A13 visual plan (``treatment``, ``template_id``,
  ``template_params``) and ``visual_asset_id`` (the scene's picture, always with a rights record).

Added only where missing: databases built after this change already get them from schema_v1.sql (0002).

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ADD = [
    "ALTER TABLE storyboards ADD COLUMN IF NOT EXISTS script_version_id uuid NULL REFERENCES script_versions",
    "ALTER TABLE storyboards ADD COLUMN IF NOT EXISTS author_type text NOT NULL DEFAULT 'AGENT'"
    " CHECK (author_type IN ('AGENT','OWNER'))",
    "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS is_hook boolean NOT NULL DEFAULT false",
    "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS pattern_interrupt boolean NOT NULL DEFAULT false",
    "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS treatment text NULL CHECK (treatment IN"
    " ('TEMPLATE','CHART','KINETIC_TEXT','OWNER_MEDIA','STOCK_SUGGESTION'))",
    "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS template_id text NULL",
    "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS template_params jsonb NULL",
    "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS visual_asset_id uuid NULL REFERENCES media_assets",
]
DROP = [
    "ALTER TABLE scenes DROP COLUMN IF EXISTS visual_asset_id",
    "ALTER TABLE scenes DROP COLUMN IF EXISTS template_params",
    "ALTER TABLE scenes DROP COLUMN IF EXISTS template_id",
    "ALTER TABLE scenes DROP COLUMN IF EXISTS treatment",
    "ALTER TABLE scenes DROP COLUMN IF EXISTS pattern_interrupt",
    "ALTER TABLE scenes DROP COLUMN IF EXISTS is_hook",
    "ALTER TABLE storyboards DROP COLUMN IF EXISTS author_type",
    "ALTER TABLE storyboards DROP COLUMN IF EXISTS script_version_id",
]


def upgrade() -> None:
    for sql in ADD:
        op.execute(sql)


def downgrade() -> None:
    for sql in DROP:
        op.execute(sql)
