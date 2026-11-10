"""Niche candidates: deterministic rescore and weight profiles (CHANNEL_DISCOVERY_SPEC §2–§3)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.db.models import NicheCandidate, ScoreWeightProfile
from tubeforge.research.scoring import PROFILES, apply_weights, check_weights, score

SIDE_PREFIX = "_"  # stored next to the criteria, e.g. {"code": "_ORIGINALITY_ANGLES", "angles": [...]}


def criteria_only(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in criteria if not str(c.get("code", "")).startswith(SIDE_PREFIX)]


def side_records(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in criteria if str(c.get("code", "")).startswith(SIDE_PREFIX)]


def default_weights(db: Session) -> dict[str, float]:
    row = db.scalar(select(ScoreWeightProfile).where(ScoreWeightProfile.is_default))
    return check_weights(row.weights if row is not None else PROFILES["Balanced"])


def profile_weights(db: Session, profile_id: uuid.UUID | str | None) -> dict[str, float]:
    if profile_id:
        row = db.get(ScoreWeightProfile, uuid.UUID(str(profile_id)))
        if row is not None:
            return check_weights(row.weights)
    return default_weights(db)


def rescore(db: Session, report_id: uuid.UUID, weights: dict[str, float]) -> list[NicheCandidate]:
    """New weights → new scores, stored. No model call (§2)."""
    w = check_weights(weights)
    rows = db.scalars(select(NicheCandidate).where(NicheCandidate.report_id == report_id)).all()
    for row in rows:
        crit = criteria_only(row.criteria)
        row.criteria = [*apply_weights(crit, w), *side_records(row.criteria)]
        row.opportunity_score = score(crit, w).value
    db.flush()
    return sorted(rows, key=lambda r: r.opportunity_score, reverse=True)
