"""Seed quota_config with the default YouTube Data API limits and costs (YOUTUBE_API_INTEGRATION Y2/Y3).

Verified on 2026-11-08 against Google's quota calculator. The ``default`` rows apply to any Cloud
project that has no rows of its own. ANALYTICS has no default: the owner enters its limits.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE = "https://developers.google.com/youtube/v3/determine_quota_cost"
ROWS: list[tuple[str, int, dict[str, int]]] = [
    ("VIDEO_UPLOADS", 100, {"videos.insert": 1}),
    ("SEARCH", 100, {"search.list": 1}),
    (
        "DEFAULT",
        10000,
        {
            "channels.list": 1,
            "videos.list": 1,
            "playlistItems.list": 1,
            "commentThreads.list": 1,
            "videos.update": 50,
            "thumbnails.set": 50,
            "playlistItems.insert": 50,
            "comments.insert": 50,
            "captions.list": 50,
            "captions.insert": 400,
            "captions.update": 450,
        },
    ),
]


def upgrade() -> None:
    for bucket, limit, costs in ROWS:
        op.execute(
            sa.text(
                "INSERT INTO quota_config (gcp_project, bucket, daily_limit, reserve_pct, research_share_pct,"
                " method_costs, verified_at, source_url) VALUES ('default', :b, :l, 10, 30,"
                " CAST(:c AS jsonb), DATE '2026-11-08', :s)"
            ).bindparams(b=bucket, l=limit, c=json.dumps(costs), s=SOURCE)
        )


def downgrade() -> None:
    op.execute("DELETE FROM quota_config WHERE gcp_project = 'default'")
