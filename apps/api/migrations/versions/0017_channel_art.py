"""Phase 8 step A: channel art (owner request 2026-11-15).

``channel_art``: the logo, banner and video-watermark variants TubeForge draws for a channel, which
blueprint each came from, and the owner's pick (one per role), shown in the Branding Studio and the
onboarding setup kit. Each file is a ``media_assets`` row with an ``asset_rights`` record.
Added only where missing: databases built after this change already get it from schema_v1.sql (0002).

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS channel_art (
          id uuid PRIMARY KEY,
          channel_id uuid NOT NULL REFERENCES channels,
          role text NOT NULL CHECK (role IN ('LOGO','BANNER','WATERMARK')),
          batch int NOT NULL,
          variant int NOT NULL,
          asset_id uuid NOT NULL REFERENCES media_assets,
          strategy_id uuid NULL REFERENCES channel_strategies,
          chosen boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS channel_art_channel_id_role_idx"
        " ON channel_art (channel_id, role) WHERE chosen"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS channel_art_channel_id_role_batch_idx"
        " ON channel_art (channel_id, role, batch)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS channel_art")
