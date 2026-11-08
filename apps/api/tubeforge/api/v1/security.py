"""Audit & security endpoints (BACKEND_SPECIFICATION §4.18)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from tubeforge.api.deps import Db, Principal, require
from tubeforge.api.pagination import Cursor, Limit, Page, clamp_limit, decode_cursor, encode_cursor
from tubeforge.audit import verify_chain
from tubeforge.db.models import AuditLog, SecurityEvent

router = APIRouter(tags=["security"])
SecurityView = Annotated[Principal, Depends(require("security.view"))]


class AuditLogOut(BaseModel):
    id: int
    occurred_at: datetime
    actor_type: str
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    channel_id: uuid.UUID | None
    details: dict[str, Any]
    request_id: uuid.UUID | None
    row_hash: str


class ChainOut(BaseModel):
    ok: bool
    checked: int
    first_broken_id: int | None


class SecurityEventOut(BaseModel):
    id: int
    occurred_at: datetime
    kind: str
    severity: str
    user_id: uuid.UUID | None
    channel_id: uuid.UUID | None
    details: dict[str, Any]


@router.get("/audit-log", response_model=Page[AuditLogOut])
def audit_log(
    db: Db,
    _: SecurityView,
    limit: Limit = None,
    cursor: Cursor = None,
    action: str | None = None,
    entity_type: str | None = None,
) -> Page[AuditLogOut]:
    n = clamp_limit(limit)
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(n + 1)
    after = decode_cursor(cursor)
    if after is not None:
        stmt = stmt.where(AuditLog.id < after)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    rows = list(db.scalars(stmt))
    more = len(rows) > n
    rows = rows[:n]
    return Page[AuditLogOut](
        items=[AuditLogOut.model_validate(r, from_attributes=True) for r in rows],
        next_cursor=encode_cursor(rows[-1].id) if more and rows else None,
    )


@router.get("/audit-log/verify-chain", response_model=ChainOut)
def audit_verify(db: Db, _: SecurityView) -> ChainOut:
    result = verify_chain(db)
    return ChainOut(ok=result.ok, checked=result.checked, first_broken_id=result.first_broken_id)


@router.get("/security-events", response_model=Page[SecurityEventOut])
def security_events(
    db: Db,
    _: SecurityView,
    limit: Limit = None,
    cursor: Cursor = None,
    kind: str | None = None,
    severity: str | None = None,
) -> Page[SecurityEventOut]:
    n = clamp_limit(limit)
    stmt = select(SecurityEvent).order_by(SecurityEvent.id.desc()).limit(n + 1)
    after = decode_cursor(cursor)
    if after is not None:
        stmt = stmt.where(SecurityEvent.id < after)
    if kind:
        stmt = stmt.where(SecurityEvent.kind == kind)
    if severity:
        stmt = stmt.where(SecurityEvent.severity == severity)
    rows = list(db.scalars(stmt))
    more = len(rows) > n
    rows = rows[:n]
    return Page[SecurityEventOut](
        items=[SecurityEventOut.model_validate(r, from_attributes=True) for r in rows],
        next_cursor=encode_cursor(rows[-1].id) if more and rows else None,
    )
