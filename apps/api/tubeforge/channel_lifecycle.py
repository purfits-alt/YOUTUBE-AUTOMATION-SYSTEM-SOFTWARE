"""Channel lifecycle helpers and onboarding steps (WORKFLOW_STATE_MACHINE §1).

State changes go through the orchestrator engine (``orchestrator/engine.py``), which owns the
channel machine table, writes ``workflow_transitions`` + audit and applies Emergency Stop rules.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.audit import Actor
from tubeforge.db.ids import uuid7
from tubeforge.db.models import Channel, OnboardingStep
from tubeforge.orchestrator import engine
from tubeforge.orchestrator.machines import CHANNEL

# from-state -> allowed to-states, derived from the orchestrator's channel machine (single source).
EDGES: dict[str, frozenset[str]] = {
    state: frozenset(e.target for e in CHANNEL.edges_from(state)) for state in CHANNEL.states
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
    """Move a channel through the orchestrator (workflow_transitions + audit in the caller's TX).

    An illegal move raises :class:`TransitionError`; Emergency Stop, actor and guard refusals raise
    :class:`~tubeforge.orchestrator.engine.TransitionRejected`."""
    if not can(channel, to_state):
        raise TransitionError(channel.state, to_state)
    engine.move(
        db,
        CHANNEL,
        channel,
        to_state,
        actor=actor,
        event_hint=event,
        idempotency_key=idempotency_key,
        reason=reason,
    )
    db.refresh(channel)


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
        try:
            transition(db, channel, "ACTIVE", event="activated", actor=actor)
        except engine.TransitionRejected:
            return False  # e.g. Emergency Stop: activation happens on the next success instead
        return True
    return False
