"""Seed the research source registry (CHANNEL_DISCOVERY_SPEC §1).

- WIKIPEDIA_PAGEVIEWS: on. Wikimedia Analytics REST API on wikimedia.org (pageview data CC0).
  ``terms_verified_at`` stays empty: the terms pages could not be opened from the build machine on
  2026-11-10, so the owner confirms them on the Sources page ("I checked the terms").
- TRENDS_API_ALPHA: off, needs the owner's approval (invitation-only alpha; no scraping).
- OWNER_NOTES and OWN_ANALYTICS: on; they are not fetched from the web.
RSS feeds and web hosts are added by the owner later; they start off and need approval.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-10
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NS = uuid.UUID("0b8f3f8e-2d55-4c1e-9a43-6f1f3c2a7e51")
# code, kind, base_url, allowed_hosts, terms_url, approval, enabled
ROWS: list[tuple[str, str, str | None, list[str], str | None, str, bool]] = [
    (
        "WIKIPEDIA_PAGEVIEWS",
        "API",
        "https://wikimedia.org/api/rest_v1/metrics/pageviews",
        ["wikimedia.org"],
        "https://www.mediawiki.org/wiki/Wikimedia_REST_API#Terms_and_conditions",
        "APPROVED",
        True,
    ),
    (
        "TRENDS_API_ALPHA",
        "API",
        None,
        [],
        "https://developers.google.com/search/apis/trends",
        "REQUIRES_OWNER_APPROVAL",
        False,
    ),
    ("OWNER_NOTES", "OWNER", None, [], None, "APPROVED", True),
    (
        "OWN_ANALYTICS",
        "OWN_ANALYTICS",
        None,
        [],
        "https://developers.google.com/youtube/terms/api-services-terms-of-service",
        "APPROVED",
        True,
    ),
]


def upgrade() -> None:
    for code, kind, base_url, hosts, terms_url, approval, enabled in ROWS:
        op.execute(
            sa.text(
                "INSERT INTO research_sources (id, code, kind, base_url, allowed_hosts, terms_url,"
                " approval_status, enabled) VALUES (:id, :code, :kind, :base_url, :hosts, :terms_url,"
                " :approval, :enabled) ON CONFLICT (code) DO NOTHING"
            ).bindparams(
                sa.bindparam("hosts", type_=sa.ARRAY(sa.Text())),
                id=uuid.uuid5(NS, code),
                code=code,
                kind=kind,
                base_url=base_url,
                hosts=hosts,
                terms_url=terms_url,
                approval=approval,
                enabled=enabled,
            )
        )


def downgrade() -> None:
    codes = sa.bindparam("codes", value=[r[0] for r in ROWS], expanding=True)
    op.execute(
        sa.text(
            "DELETE FROM source_documents WHERE source_id IN"
            " (SELECT id FROM research_sources WHERE code IN :codes)"
        ).bindparams(codes)
    )
    op.execute(sa.text("DELETE FROM research_sources WHERE code IN :codes").bindparams(codes))
