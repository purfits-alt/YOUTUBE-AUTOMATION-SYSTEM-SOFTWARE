"""Approval requests bound to the exact content they approve (WORKFLOW_STATE_MACHINE §7).

Every owner gate creates an approval request carrying a SHA-256 of the subject (for an upload: the
render file, SEO package, thumbnail and upload choices). A decision must name the same hash; if
the subject changed meanwhile the request is EXPIRED (``APPROVAL_STALE``). Changing the subject
after approval INVALIDATES the approval, so downstream guards refuse to act on it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.audit import SYSTEM, Actor, record
from tubeforge.db.ids import uuid7
from tubeforge.db.models import ApprovalRequest
from tubeforge.notifications import notify_owners
from tubeforge.orchestrator import engine
from tubeforge.orchestrator.machines import APPROVAL

DEFAULT_TTL = timedelta(days=14)
Decision = Literal["APPROVE", "REQUEST_CHANGES", "REJECT"]
_EVENT = {"APPROVE": "approve", "REQUEST_CHANGES": "request_changes", "REJECT": "reject"}


class ApprovalStale(Exception):  # noqa: N818 - API code APPROVAL_STALE
    """The subject changed since the approval was requested; the request is now EXPIRED."""


def request(
    db: Session,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
    subject_sha256: str,
    channel_id: uuid.UUID | None,
    actor: Actor,
    payload: dict[str, Any] | None = None,
    ttl: timedelta = DEFAULT_TTL,
    now: datetime | None = None,
) -> ApprovalRequest:
    """Open (or return the already-open) request for this exact subject content."""
    now = now or datetime.now(UTC)
    open_rows = db.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.subject_type == subject_type,
            ApprovalRequest.subject_id == subject_id,
            ApprovalRequest.state == "PENDING",
        )
    ).all()
    for row in open_rows:
        if row.subject_sha256 == subject_sha256:
            return row
        engine.transition(db, APPROVAL, row.id, "expire", actor=SYSTEM, reason="subject changed")
    row = ApprovalRequest(
        id=uuid7(),
        channel_id=channel_id,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_sha256=subject_sha256,
        state="PENDING",
        requested_by_type=actor.type,
        requested_at=now,
        payload=payload or {},
        expires_at=now + ttl,
    )
    db.add(row)
    db.flush()
    record(
        db,
        actor=actor,
        action="approval.requested",
        entity_type="approval_request",
        entity_id=str(row.id),
        channel_id=channel_id,
        details={"subject_type": subject_type, "subject_id": str(subject_id)},
    )
    notify_owners(
        db,
        event_type="approval.requested",
        severity="INFO",
        title="Your approval is needed",
        body=f"{subject_type.replace('_', ' ').title()} is waiting for your decision.",
        dedup_key=f"approval:{row.id}",
        channel_id=channel_id,
        link="/approvals",
        entity_type="approval_request",
        entity_id=row.id,
        now=now,
    )
    return row


def decide(
    db: Session,
    approval_id: uuid.UUID,
    decision: Decision,
    *,
    actor: Actor,
    actor_user_id: uuid.UUID | None,
    subject_sha256: str,
    comment: str | None = None,
    auto_rule_id: str | None = None,
    idempotency_key: str | None = None,
    now: datetime | None = None,
) -> ApprovalRequest:
    now = now or datetime.now(UTC)
    row = db.get(ApprovalRequest, approval_id)
    if row is None:
        raise engine.TransitionRejected("NOT_FOUND", ["No such approval request."])
    if row.state == "PENDING" and row.subject_sha256 != subject_sha256:
        engine.transition(
            db, APPROVAL, row.id, "expire", actor=SYSTEM, reason="subject changed before decision"
        )
        raise ApprovalStale(str(approval_id))
    payload = {"subject_sha256": subject_sha256, "comment": comment, "auto_rule_id": auto_rule_id}
    engine.transition(
        db,
        APPROVAL,
        row.id,
        _EVENT[decision],
        actor=actor,
        payload=payload,
        idempotency_key=idempotency_key,
        reason=comment,
        now=now,
    )
    db.refresh(row)
    if row.decided_at is None:
        row.decided_by = actor_user_id
        row.decided_at = now
        row.comment = comment
        row.auto_rule_id = auto_rule_id
        db.flush()
    return row


def invalidate_subject(
    db: Session, *, subject_type: str, subject_id: uuid.UUID, new_sha256: str, actor: Actor = SYSTEM
) -> int:
    """The subject's content changed: approvals of other content no longer count."""
    n = 0
    rows = db.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.subject_type == subject_type,
            ApprovalRequest.subject_id == subject_id,
            ApprovalRequest.state.in_(("PENDING", "APPROVED")),
            ApprovalRequest.subject_sha256 != new_sha256,
        )
    ).all()
    for row in rows:
        event = "invalidate" if row.state == "APPROVED" else "expire"
        engine.transition(db, APPROVAL, row.id, event, actor=actor, reason="subject content changed")
        n += 1
    return n


def expire_due(db: Session, *, now: datetime | None = None) -> int:
    """Periodic: PENDING requests past their deadline (default 14 days) expire."""
    now = now or datetime.now(UTC)
    ids = db.scalars(
        select(ApprovalRequest.id).where(ApprovalRequest.state == "PENDING", ApprovalRequest.expires_at < now)
    ).all()
    for aid in ids:
        engine.transition(db, APPROVAL, aid, "expire", actor=SYSTEM, reason="no decision in time", now=now)
    return len(ids)
