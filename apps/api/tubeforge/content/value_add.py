"""Owner value-add score (0–100): what the owner adds that an AI cannot (F3 defence).

Defined in Phase 7 (VIDEO_PRODUCTION_SPEC §1b). Text counts once it says something real
(≥ 30 characters). Voice is scored separately in the originality score (AUDIT_AND_POLICY_SPEC).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

MIN_CHARS = 30
POINTS: dict[str, int] = {
    "own_experience": 25,
    "own_opinion": 20,
    "own_data": 20,
    "own_examples": 15,
    "owner_footage": 12,
    "owner_photos": 8,
}
TEXT_FIELDS = ("own_experience", "own_opinion", "own_data", "own_examples")


def filled_fields(values: dict[str, Any]) -> list[str]:
    out = [k for k in TEXT_FIELDS if len(str(values.get(k) or "").strip()) >= MIN_CHARS]
    out += [k for k in ("owner_footage", "owner_photos") if values.get(k) is True]
    return out


def score(values: dict[str, Any]) -> Decimal:
    return Decimal(min(100, sum(POINTS[k] for k in filled_fields(values)))).quantize(Decimal("0.01"))
