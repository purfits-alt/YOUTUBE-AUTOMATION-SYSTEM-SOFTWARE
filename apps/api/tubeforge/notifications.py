"""Minimal in-app notifications (NOTIFICATION_SPEC; Telegram/email delivery arrives in Phase 12)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.db.ids import uuid7
from tubeforge.db.models import Notification, Role, UserRole


def owner_ids(db: Session) -> list[uuid.UUID]:
    rows = db.scalars(
        select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.name == "OWNER")
    ).all()
    return sorted(set(rows))


def notify_owners(
    db: Session,
    *,
    event_type: str,
    severity: str,
    title: str,
    body: str,
    dedup_key: str,
    dedup_window: timedelta = timedelta(0),
    channel_id: uuid.UUID | None = None,
    link: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> int:
    """Add one notification per owner unless the same dedup_key was sent within ``dedup_window``.

    Returns how many were added.
    """
    now = now or datetime.now(UTC)
    if dedup_window > timedelta(0):
        recent = db.scalar(
            select(Notification.id)
            .where(Notification.dedup_key == dedup_key, Notification.created_at > now - dedup_window)
            .limit(1)
        )
        if recent is not None:
            return 0
    added = 0
    for user_id in owner_ids(db):
        db.add(
            Notification(
                id=uuid7(),
                user_id=user_id,
                channel_id=channel_id,
                event_type=event_type,
                severity=severity,
                title=title,
                body=body,
                link=link,
                entity_type=entity_type,
                entity_id=entity_id,
                dedup_key=dedup_key,
                created_at=now,
            )
        )
        added += 1
    db.flush()
    return added
