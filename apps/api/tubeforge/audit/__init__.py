"""Audit log with a SHA-256 hash chain, and security events (DATABASE_SCHEMA §1, BACKEND_SPECIFICATION §1).

row_hash = sha256(prev_hash || canonical JSON of the row). The first row's prev_hash is 64 zeros.
Writers take a transaction-scoped advisory lock, so two concurrent writes cannot both chain onto
the same predecessor. The table is append-only (trigger), so verification detects any edit made
around the application (e.g. with superuser rights).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from tubeforge.db.models import AuditLog, SecurityEvent
from tubeforge.logging import redact_value

GENESIS = "0" * 64
_LOCK_KEY = 0x7F4A_0D17  # pg_advisory_xact_lock key reserved for the audit chain


def content_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _canonical(row: AuditLog) -> str:
    return json.dumps(
        {
            "occurred_at": row.occurred_at.astimezone(UTC).isoformat(),
            "actor_type": row.actor_type,
            "actor_id": row.actor_id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "channel_id": str(row.channel_id) if row.channel_id else None,
            "before_sha256": row.before_sha256,
            "after_sha256": row.after_sha256,
            "details": row.details,
            "request_id": str(row.request_id) if row.request_id else None,
            "ip": str(row.ip) if row.ip else None,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _row_hash(prev_hash: str, row: AuditLog) -> str:
    return hashlib.sha256((prev_hash + _canonical(row)).encode()).hexdigest()


def _redacted(details: dict[str, Any] | None) -> dict[str, Any]:
    cleaned = redact_value(details or {})
    return cleaned if isinstance(cleaned, dict) else {}


@dataclass(frozen=True)
class Actor:
    type: str  # OWNER, USER, AGENT, AUDITOR, SYSTEM, ORCH
    id: str


SYSTEM = Actor("SYSTEM", "system")


def record(
    db: Session,
    *,
    actor: Actor,
    action: str,
    entity_type: str,
    entity_id: str,
    channel_id: uuid.UUID | None = None,
    before: Any = None,
    after: Any = None,
    details: dict[str, Any] | None = None,
    request_id: uuid.UUID | None = None,
    ip: str | None = None,
) -> AuditLog:
    """Append one audit row in the caller's transaction (details are redacted)."""
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
    prev = db.scalar(select(AuditLog.row_hash).order_by(AuditLog.id.desc()).limit(1)) or GENESIS
    row = AuditLog(
        occurred_at=datetime.now(UTC),  # set here (not by the DB) so the hash covers it exactly
        actor_type=actor.type,
        actor_id=actor.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        channel_id=channel_id,
        before_sha256=content_sha256(before) if before is not None else None,
        after_sha256=content_sha256(after) if after is not None else None,
        details=_redacted(details),
        request_id=request_id,
        ip=ip,
        prev_hash=prev,
        row_hash="",
    )
    row.row_hash = _row_hash(prev, row)
    db.add(row)
    db.flush()
    return row


@dataclass(frozen=True)
class ChainResult:
    ok: bool
    checked: int
    first_broken_id: int | None


def verify_chain(db: Session, batch: int = 1000) -> ChainResult:
    prev = GENESIS
    checked = 0
    last_id = 0
    while True:
        rows = db.scalars(
            select(AuditLog).where(AuditLog.id > last_id).order_by(AuditLog.id).limit(batch)
        ).all()
        if not rows:
            return ChainResult(ok=True, checked=checked, first_broken_id=None)
        for row in rows:
            if row.prev_hash != prev or _row_hash(prev, row) != row.row_hash:
                return ChainResult(ok=False, checked=checked, first_broken_id=row.id)
            prev = row.row_hash
            checked += 1
            last_id = row.id


def security_event(
    db: Session,
    kind: str,
    severity: str = "INFO",
    *,
    user_id: uuid.UUID | None = None,
    channel_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        SecurityEvent(
            kind=kind, severity=severity, user_id=user_id, channel_id=channel_id, details=_redacted(details)
        )
    )
    db.flush()
