"""Channel state machine (WORKFLOW_STATE_MACHINE §1) and onboarding steps.

Every state change goes through :func:`transition`, which checks the edge, writes a
``workflow_transitions`` row and an audit row in the caller's transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.audit import Actor, record
from tubeforge.db.ids import uuid7
from tubeforge.db.models import Channel, OnboardingStep, WorkflowTransition

# from-state -> allowed to-states (the diagram, plus pausing/disconnecting a CONNECTED channel and
# disconnecting a PAUSED one, which the owner needs before a channel is ACTIVE).
EDGES: dict[str, frozenset[str]] = {
    "PROPOSED": frozenset({"APPROVED", "REJECTED"}),
    "APPROVED": frozenset({"ONBOARDING"}),
    "ONBOARDING": frozenset({"CONNECTED", "DISCONNECTING"}),
    "CONNECTED": frozenset({"ACTIVE", "PAUSED", "NEEDS_REAUTH", "DISCONNECTING"}),
    "ACTIVE": frozenset({"PAUSED", "NEEDS_REAUTH", "DISCONNECTING"}),
    "PAUSED": frozenset({"ACTIVE", "CONNECTED", "NEEDS_REAUTH", "DISCONNECTING"}),
    "NEEDS_REAUTH": frozenset({"ACTIVE", "CONNECTED", "PAUSED", "DISCONNECTING"}),
    "DISCONNECTING": frozenset({"DISCONNECTED"}),
    "DISCONNECTED": frozenset({"ONBOARDING"}),
    "REJECTED": frozenset(),
}

ONBOARDING_STEPS = (
    "CREATE_GOOGLE_ACCOUNT",
    "CREATE_CHANNEL",
    "VERIFY_PHONE",
    "CREATE_GCP_PROJECT",
    "ENABLE_APIS",
    "CONSENT_SCREEN",
    "OAUTH_CLIENT",
    "PRIVACY_POLICY",
    "CONNECT",
    "TEST_UPLOAD",
)


class TransitionError(Exception):
    def __init__(self, from_state: str, to_state: str) -> None:
        super().__init__(f"{from_state} -> {to_state} is not allowed")
        self.from_state = from_state
        self.to_state = to_state


def can(channel: Channel, to_state: str) -> bool:
    return to_state in EDGES.get(channel.state, frozenset())


def transition(
    db: Session,
    channel: Channel,
    to_state: str,
    *,
    event: str,
    actor: Actor,
    idempotency_key: str | None = None,
    reason: str | None = None,
) -> None:
    from_state = channel.state
    if not can(channel, to_state):
        raise TransitionError(from_state, to_state)
    channel.state = to_state
    db.add(
        WorkflowTransition(
            entity_type="channel",
            entity_id=channel.id,
            channel_id=channel.id,
            from_state=from_state,
            to_state=to_state,
            event=event,
            actor_type=actor.type,
            actor_id=actor.id,
            reason=reason,
            idempotency_key=idempotency_key or str(uuid7()),
        )
    )
    record(
        db,
        actor=actor,
        action=f"channel.{event}",
        entity_type="channel",
        entity_id=str(channel.id),
        channel_id=channel.id,
        before={"state": from_state},
        after={"state": to_state},
        details={"reason": reason} if reason else None,
    )
    db.flush()


def ensure_onboarding_steps(db: Session, channel: Channel) -> list[OnboardingStep]:
    """Create any missing steps (idempotent) and return all ten in order."""
    existing = {
        s.step_code: s
        for s in db.scalars(select(OnboardingStep).where(OnboardingStep.channel_id == channel.id))
    }
    for code in ONBOARDING_STEPS:
        if code not in existing:
            step = OnboardingStep(id=uuid7(), channel_id=channel.id, step_code=code, status="TODO")
            db.add(step)
            existing[code] = step
    db.flush()
    return [existing[c] for c in ONBOARDING_STEPS]


def mark_step(db: Session, channel_id: object, code: str, status: str = "DONE") -> None:
    step = db.scalar(
        select(OnboardingStep).where(
            OnboardingStep.channel_id == channel_id, OnboardingStep.step_code == code
        )
    )
    if step is not None and step.status != status:
        step.status = status
        step.completed_at = datetime.now(UTC) if status == "DONE" else None
        db.flush()


def reset_connection_steps(db: Session, channel: Channel) -> None:
    for code in ("CONNECT", "TEST_UPLOAD"):
        mark_step(db, channel.id, code, "TODO")


def maybe_activate(db: Session, channel: Channel, *, actor: Actor) -> bool:
    """CONNECTED → ACTIVE once ≥ 1 private test upload succeeded and a privacy-policy URL is set."""
    if (
        channel.state == "CONNECTED"
        and channel.successful_private_test_uploads >= 1
        and bool(channel.privacy_policy_url)
    ):
        transition(db, channel, "ACTIVE", event="activated", actor=actor)
        return True
    return False
