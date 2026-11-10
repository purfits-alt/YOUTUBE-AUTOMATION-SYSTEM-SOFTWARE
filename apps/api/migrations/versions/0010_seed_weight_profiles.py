"""Seed the score weight profiles (CHANNEL_DISCOVERY_SPEC §2): Balanced (default), Originality-first,
Low effort on H-LITE. Weights are copied here (frozen), not imported, so the migration never changes.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-10
"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NS = uuid.UUID("7c1d5b1e-4f0a-4e1f-8a8b-2b8f0d6e9c33")
BALANCED = {
    "AUDIENCE_DEMAND": 8, "SEARCH_INTEREST": 6, "RISING_TOPICS": 5, "EVERGREEN": 7, "COMPETITION_LEVEL": 4,
    "ADVERTISER_SUITABILITY": 6, "PRODUCTION_FEASIBILITY": 9, "ORIGINALITY_OPPORTUNITY": 9,
    "LONG_FORM_POTENTIAL": 5, "SHORTS_POTENTIAL": 4, "INAUTHENTIC_RISK_INVERSE": 10,
}  # fmt: skip
PROFILES = [
    ("Balanced", BALANCED, True),
    (
        "Originality-first",
        {**BALANCED, "ORIGINALITY_OPPORTUNITY": 13.5, "INAUTHENTIC_RISK_INVERSE": 15},
        False,
    ),
    ("Low effort on H-LITE", {**BALANCED, "PRODUCTION_FEASIBILITY": 13.5}, False),
]


def upgrade() -> None:
    for name, weights, default in PROFILES:
        op.execute(
            sa.text(
                "INSERT INTO score_weight_profiles (id, name, weights, is_default)"
                " VALUES (:id, :name, CAST(:weights AS jsonb), :d) ON CONFLICT (name) DO NOTHING"
            ).bindparams(id=uuid.uuid5(NS, name), name=name, weights=json.dumps(weights), d=default)
        )


def downgrade() -> None:
    names = sa.bindparam("names", value=[p[0] for p in PROFILES], expanding=True)
    op.execute(sa.text("DELETE FROM score_weight_profiles WHERE name IN :names").bindparams(names))
