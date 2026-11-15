"""Phase 7 step B: idea packaging promise + Wikipedia articles research source.

- ``video_ideas.packaging_promise`` (jsonb) and ``owner_value_add_prompt`` (text): A08 drafts them
  with each idea; the promise is copied to the project when the idea is approved. Added only where
  missing: databases built after this change already get them from schema_v1.sql (0002).
- ``WIKIPEDIA_ARTICLES``: plain-text article extracts and search for A09 research, on the five
  channel-language Wikipedias. Text is CC BY-SA 4.0: briefs quote short passages and keep the URL.
  ``terms_verified_at`` stays empty: the owner confirms the terms on the Sources page.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-15
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NS = uuid.UUID("0b8f3f8e-2d55-4c1e-9a43-6f1f3c2a7e51")  # same namespace as 0009
CODE = "WIKIPEDIA_ARTICLES"
HOSTS = [f"{lang}.wikipedia.org" for lang in ("en", "es", "fr", "de", "ur")]


def upgrade() -> None:
    op.execute("ALTER TABLE video_ideas ADD COLUMN IF NOT EXISTS packaging_promise jsonb NULL")
    op.execute("ALTER TABLE video_ideas ADD COLUMN IF NOT EXISTS owner_value_add_prompt text NULL")
    op.execute(
        sa.text(
            "INSERT INTO research_sources (id, code, kind, base_url, allowed_hosts, terms_url,"
            " approval_status, enabled) VALUES (:id, :code, 'API', :base_url, :hosts, :terms_url,"
            " 'APPROVED', true) ON CONFLICT (code) DO NOTHING"
        ).bindparams(
            sa.bindparam("hosts", type_=sa.ARRAY(sa.Text())),
            id=uuid.uuid5(NS, CODE),
            code=CODE,
            base_url="https://en.wikipedia.org/w/api.php",
            hosts=HOSTS,
            terms_url="https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use",
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM source_documents"
            " WHERE source_id IN (SELECT id FROM research_sources WHERE code = :c)"
        ).bindparams(c=CODE)
    )
    op.execute(sa.text("DELETE FROM research_sources WHERE code = :c").bindparams(c=CODE))
    op.execute("ALTER TABLE video_ideas DROP COLUMN IF EXISTS owner_value_add_prompt")
    op.execute("ALTER TABLE video_ideas DROP COLUMN IF EXISTS packaging_promise")
