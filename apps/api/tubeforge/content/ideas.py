"""Idea helpers shared by the API and the workers: similarity to the channel's earlier ideas (ADR-0029)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.content import similarity
from tubeforge.db.models import VideoIdea


@dataclass(frozen=True)
class Closest:
    score: Decimal | None
    idea_id: uuid.UUID | None


def as_decimal(x: float) -> Decimal:
    return Decimal(str(round(min(max(x, 0.0), 1.0), 3)))


def closest_idea(
    db: Session, channel_id: uuid.UUID, title: str, *, exclude: uuid.UUID | None = None
) -> Closest:
    """The most similar earlier idea title on the channel (any state, not deleted)."""
    stmt = select(VideoIdea.id, VideoIdea.title).where(
        VideoIdea.channel_id == channel_id, VideoIdea.deleted_at.is_(None)
    )
    if exclude is not None:
        stmt = stmt.where(VideoIdea.id != exclude)
    rows = db.execute(stmt).all()
    near = similarity.nearest(title, [r.title for r in rows])
    if near.index is None:
        return Closest(None, None)
    return Closest(as_decimal(near.score), rows[near.index].id)


def similarity_flags(score: Decimal | None) -> tuple[bool, bool]:
    """(duplicate, maybe_same_idea_in_other_words) under the installed method's limits."""
    if score is None:
        return False, False
    limits = similarity.limits_for()
    value = float(score)
    duplicate = value >= limits.duplicate
    band = limits.paraphrase_warning
    paraphrase = band is not None and band <= value < limits.duplicate
    return duplicate, paraphrase
