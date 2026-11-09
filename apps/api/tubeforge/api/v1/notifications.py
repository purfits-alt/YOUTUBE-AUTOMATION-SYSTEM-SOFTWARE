"""In-app notifications for the signed-in user (BACKEND_SPECIFICATION §4.16, minimal in Phase 4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import func, select, update

from tubeforge.api.deps import Db, Principal, authenticated
from tubeforge.api.errors import not_found
from tubeforge.api.pagination import Cursor, Limit, Page, clamp_limit
from tubeforge.api.v1.channels import uuid_cursor
from tubeforge.db.models import Notification

router = APIRouter(tags=["notifications"])
Me = Annotated[Principal, Depends(authenticated)]
Severity = Literal["INFO", "WARNING", "CRITICAL"]


class NotificationOut(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID | None
    event_type: str
    severity: Severity
    title: str
    body: str
    link: str | None
    created_at: datetime
    read_at: datetime | None


class SummaryOut(BaseModel):
    unread: int
    critical_unread: int


@router.get("/notifications", response_model=Page[NotificationOut])
def list_notifications(
    db: Db,
    p: Me,
    limit: Limit = None,
    cursor: Cursor = None,
    unread: bool | None = None,
    severity: Severity | None = None,
    channel_id: uuid.UUID | None = None,
) -> Page[NotificationOut]:
    n = clamp_limit(limit)
    stmt = select(Notification).where(Notification.user_id == p.user.id).order_by(Notification.id.desc())
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    if severity:
        stmt = stmt.where(Notification.severity == severity)
    if channel_id:
        stmt = stmt.where(Notification.channel_id == channel_id)
    after = uuid_cursor(cursor)
    if after is not None:
        stmt = stmt.where(Notification.id < after)
    rows = list(db.scalars(stmt.limit(n + 1)))
    more = len(rows) > n
    rows = rows[:n]
    return Page[NotificationOut](
        items=[NotificationOut.model_validate(r, from_attributes=True) for r in rows],
        next_cursor=f"c{rows[-1].id.int}" if more and rows else None,
    )


@router.get("/notifications/summary", response_model=SummaryOut)
def summary(db: Db, p: Me) -> SummaryOut:
    """The bell: unread count and how many of them are critical."""
    base = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == p.user.id, Notification.read_at.is_(None))
    )
    unread = int(db.scalar(base) or 0)
    critical = int(db.scalar(base.where(Notification.severity == "CRITICAL")) or 0)
    return SummaryOut(unread=unread, critical_unread=critical)


@router.post("/notifications/{notification_id}/read", status_code=204)
def mark_read(notification_id: uuid.UUID, db: Db, p: Me) -> Response:
    row = db.get(Notification, notification_id)
    if row is None or row.user_id != p.user.id:
        raise not_found("No such notification.")
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        db.commit()
    return Response(status_code=204)


@router.post("/notifications/read-all", status_code=204)
def mark_all_read(db: Db, p: Me) -> Response:
    db.execute(
        update(Notification)
        .where(Notification.user_id == p.user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    db.commit()
    return Response(status_code=204)
