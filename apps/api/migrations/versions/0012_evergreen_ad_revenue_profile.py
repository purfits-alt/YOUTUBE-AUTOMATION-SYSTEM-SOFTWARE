"""Add the "Evergreen ad revenue" score weight profile and make it the default (owner request).

The owner's goal is steady ad income from long-lasting views: evergreen interest, advertiser-
friendly topics, demand, search interest and long-form potential weigh most; the inauthentic-
content guard stays heavy because ad income needs YPP. The default only moves if it is still the
seeded "Balanced" one. Weights are a frozen copy (CHANNEL_DISCOVERY_SPEC §2).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-12
"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NS = uuid.UUID("7c1d5b1e-4f0a-4e1f-8a8b-2b8f0d6e9c33")  # same namespace as 0010
NAME = "Evergreen ad revenue"
WEIGHTS = {
    "AUDIENCE_DEMAND": 12, "SEARCH_INTEREST": 11, "RISING_TOPICS": 6, "EVERGREEN": 15, "COMPETITION_LEVEL": 6,
    "ADVERTISER_SUITABILITY": 14, "PRODUCTION_FEASIBILITY": 8, "ORIGINALITY_OPPORTUNITY": 9,
    "LONG_FORM_POTENTIAL": 11, "SHORTS_POTENTIAL": 5, "INAUTHENTIC_RISK_INVERSE": 12,
}  # fmt: skip


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO score_weight_profiles (id, name, weights, is_default)"
            " VALUES (:id, :name, CAST(:weights AS jsonb), false) ON CONFLICT (name) DO NOTHING"
        ).bindparams(id=uuid.uuid5(NS, NAME), name=NAME, weights=json.dumps(WEIGHTS))
    )
    # Move the default only if the owner has not picked another one.
    op.execute(
        sa.text(
            "UPDATE score_weight_profiles SET is_default = (name = :name)"
            " WHERE EXISTS (SELECT 1 FROM score_weight_profiles WHERE is_default AND name = 'Balanced')"
        ).bindparams(name=NAME)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE score_weight_profiles SET is_default = (name = 'Balanced')"
            " WHERE EXISTS (SELECT 1 FROM score_weight_profiles WHERE is_default AND name = :name)"
        ).bindparams(name=NAME)
    )
    op.execute(sa.text("DELETE FROM score_weight_profiles WHERE name = :name").bindparams(name=NAME))
