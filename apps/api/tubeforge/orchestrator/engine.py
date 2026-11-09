"""The transition engine — the only code that changes a workflow state (WORKFLOW_STATE_MACHINE §0).

One call = one step inside the caller's transaction:
1. replay check — ``(entity_id, idempotency_key)`` already done → return the earlier result
2. lock the entity row (``SELECT … FOR UPDATE``)
3. Emergency Stop blocks everything except moves to PAUSED / CANCELLED and safety moves
4. find the edge for (state, event); universal PAUSED / CANCELLED / FAILED for project-like machines
5. actor rules and mode gates (MANUAL / SEMI [S] / FULLY [F])
6. every guard (all failures are reported together)
7. write the state, a ``workflow_transitions`` row and an ``audit_log`` row; run on-enter effects

Rejections raise :class:`TransitionRejected` with a stable code and the reasons.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.audit import Actor, record, security_event
from tubeforge.db.ids import uuid7
from tubeforge.db.models import Channel, SystemSettings, WorkflowTransition
from tubeforge.notifications import notify_owners
from tubeforge.orchestrator.guards import GUARDS, GuardContext
from tubeforge.orchestrator.machines import AGENT, AUDITOR, ORCH, OWNER, SYSTEM, Edge, Machine

HUMAN_TYPES = {"OWNER", "USER"}  # API users; their permissions were checked by the route
ACTOR_TYPES = {OWNER, ORCH, AGENT, AUDITOR, SYSTEM}
UNIVERSAL_EVENTS = {"pause", "resume", "cancel", "fail", "retry"}
SYSTEM_RESUME_REASONS = {"quota", "resources"}


class TransitionRejected(Exception):  # noqa: N818 - domain wording
    def __init__(self, code: str, reasons: list[str]) -> None:
        super().__init__(f"{code}: {'; '.join(reasons)}")
        self.code = code
        self.reasons = reasons


@dataclass(frozen=True)
class TransitionResult:
    entity_id: uuid.UUID
    from_state: str
    to_state: str
    event: str
    replayed: bool
    transition_id: int | None


def actor_class(actor: Actor) -> str:
    """OWNER for humans (OWNER/USER); AGENT, AUDITOR, ORCH and SYSTEM as is (the id names which one)."""
    kind = actor.type
    if kind in HUMAN_TYPES:
        return OWNER
    if kind not in ACTOR_TYPES:
        raise TransitionRejected("UNKNOWN_ACTOR", [f"unknown actor type {actor.type}"])
    return kind


# ------------------------------------------------------------------------------------- effects
Effect = Callable[[Session, Machine, Any, TransitionResult, Actor], None]
ON_ENTER: dict[tuple[str, str], list[Effect]] = {}


def on_enter(entity_type: str, state: str) -> Callable[[Effect], Effect]:
    def register(fn: Effect) -> Effect:
        ON_ENTER.setdefault((entity_type, state), []).append(fn)
        return fn

    return register


@on_enter("voice_profile", "REJECTED")
def _voice_rejected(
    db: Session, machine: Machine, entity: Any, result: TransitionResult, actor: Actor
) -> None:
    security_event(db, "VOICE_VERIFICATION_REJECTED", "WARNING", user_id=entity.owner_user_id)


def _notify_project(severity: str, title: str) -> Effect:
    def effect(db: Session, machine: Machine, entity: Any, result: TransitionResult, actor: Actor) -> None:
        notify_owners(
            db,
            event_type=f"project.{result.to_state.lower()}",
            severity=severity,
            title=title,
            body=f"“{entity.working_title}” moved from {result.from_state} to {result.to_state}.",
            dedup_key=f"project:{entity.id}:{result.to_state}:{result.transition_id}",
            channel_id=entity.channel_id,
            link=f"/projects/{entity.id}",
            entity_type="video_project",
            entity_id=entity.id,
        )

    return effect


on_enter("video_project", "FAILED")(_notify_project("WARNING", "A project needs you"))
on_enter("video_project", "BLOCKED")(_notify_project("WARNING", "A project is blocked by an audit"))
on_enter("video_project", "READY_FOR_APPROVAL")(_notify_project("INFO", "A video is ready for your approval"))


# -------------------------------------------------------------------------------------- engine
@dataclass
class _Plan:
    edge: Edge | None
    target: str
    universal: bool = False
    gate_auto: bool = False
    reasons: list[str] = field(default_factory=list)


def emergency_stop_active(db: Session) -> bool:
    row = db.get(SystemSettings, 1)
    return bool(row and row.emergency_stop)


def _channel_of(db: Session, machine: Machine, entity: Any) -> Channel | None:
    if machine.channel_attr is None:
        return None
    cid = getattr(entity, machine.channel_attr, None)
    return db.get(Channel, cid) if cid else None


def _gate_allows_orch(edge: Edge, channel: Channel | None, payload: dict[str, Any]) -> tuple[bool, str]:
    mode = channel.operating_mode if channel else "MANUAL"
    if edge.gate is None:
        return False, "Only " + ", ".join(sorted(edge.actors)) + " may do this."
    if mode == "MANUAL":
        return False, "Manual mode: the owner decides this step."
    if mode == "SEMI_AUTOMATIC":
        if "S" in edge.gate:
            return False, "Semi-automatic mode: the owner still decides this step."
        return True, ""
    if "F" in edge.gate:
        return False, "This step always needs the owner."
    if not payload.get("auto_rule_id"):
        return False, "Fully automatic mode: an accepted auto-publish rule must cover this step."
    return True, ""


def _plan(
    machine: Machine, entity: Any, event: str, who: str, payload: dict[str, Any], channel: Channel | None
) -> _Plan:
    state = entity.state
    if state in machine.terminal:
        raise TransitionRejected(
            "TERMINAL_STATE", [f"{machine.entity_type} is {state}; nothing more can happen."]
        )
    if machine.universal and event in UNIVERSAL_EVENTS:
        return _plan_universal(machine, entity, state, event, who, payload)
    edge = machine.edge(state, event)
    if edge is None:
        raise TransitionRejected("INVALID_TRANSITION", [f"“{event}” is not possible from {state}."])
    plan = _Plan(edge=edge, target=edge.target)
    if who not in edge.actors:
        allowed, why = (False, f"Only {', '.join(sorted(edge.actors))} may do this.")
        if who == ORCH:
            allowed, why = _gate_allows_orch(edge, channel, payload)
        if not allowed:
            raise TransitionRejected("ACTOR_NOT_ALLOWED", [why])
        plan.gate_auto = True
    return plan


def _plan_universal(
    machine: Machine, entity: Any, state: str, event: str, who: str, payload: dict[str, Any]
) -> _Plan:
    resume_to = getattr(entity, "resume_to_state", None)
    if event == "pause":
        if state == "PAUSED":
            raise TransitionRejected("INVALID_TRANSITION", ["Already paused."])
        if who not in {OWNER, SYSTEM, ORCH}:
            raise TransitionRejected("ACTOR_NOT_ALLOWED", ["Only the owner or the system can pause."])
        return _Plan(edge=None, target="PAUSED", universal=True)
    if event == "cancel":
        if who != OWNER:
            raise TransitionRejected("ACTOR_NOT_ALLOWED", ["Only the owner can cancel."])
        return _Plan(edge=None, target="CANCELLED", universal=True)
    if event == "fail":
        if state == "FAILED" or who not in {SYSTEM, AGENT, ORCH}:
            raise TransitionRejected("ACTOR_NOT_ALLOWED", ["Only the system or an agent reports a failure."])
        return _Plan(edge=None, target="FAILED", universal=True)
    if event == "resume":
        if state != "PAUSED" or not resume_to:
            raise TransitionRejected("INVALID_TRANSITION", ["Only a paused item can resume."])
        system_ok = who == SYSTEM and payload.get("reason") in SYSTEM_RESUME_REASONS
        if who != OWNER and not system_ok:
            raise TransitionRejected(
                "ACTOR_NOT_ALLOWED", ["Resuming needs the owner (system only after quota/resource waits)."]
            )
        return _Plan(edge=None, target=resume_to, universal=True)
    # retry
    if state != "FAILED" or not resume_to:
        raise TransitionRejected("INVALID_TRANSITION", ["Only a failed item can be retried."])
    if who != OWNER:
        raise TransitionRejected("ACTOR_NOT_ALLOWED", ["Only the owner can retry."])
    return _Plan(edge=None, target=resume_to, universal=True)


def transition(
    db: Session,
    machine: Machine,
    entity_id: uuid.UUID,
    event: str,
    *,
    actor: Actor,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    reason: str | None = None,
    now: datetime | None = None,
) -> TransitionResult:
    payload = dict(payload or {})
    now = now or datetime.now(UTC)
    key = idempotency_key or str(uuid7())
    done = db.scalar(
        select(WorkflowTransition).where(
            WorkflowTransition.entity_id == entity_id, WorkflowTransition.idempotency_key == key
        )
    )
    if done is not None:
        return TransitionResult(entity_id, done.from_state, done.to_state, done.event, True, done.id)

    entity = db.get(machine.model, entity_id, with_for_update=True, populate_existing=True)
    if entity is None or getattr(entity, "deleted_at", None) is not None:
        raise TransitionRejected("NOT_FOUND", [f"No such {machine.entity_type}."])
    who = actor_class(actor)
    channel = _channel_of(db, machine, entity)
    plan = _plan(machine, entity, event, who, payload, channel)

    exempt = plan.target in {"PAUSED", "CANCELLED"} or (plan.edge is not None and plan.edge.es_exempt)
    if emergency_stop_active(db) and not exempt:
        raise TransitionRejected(
            "EMERGENCY_STOP", ["Emergency Stop is on; only pausing or cancelling is possible."]
        )

    if plan.edge is not None:
        ctx = GuardContext(db, machine, entity, plan.edge, who, payload, channel, now)
        failures = [msg for name in plan.edge.guards if (msg := GUARDS[name](ctx)) is not None]
        if failures:
            raise TransitionRejected("GUARD_FAILED", failures)

    from_state: str = entity.state
    if plan.universal and plan.target in {"PAUSED", "FAILED"} and hasattr(entity, "resume_to_state"):
        entity.resume_to_state = from_state
    elif plan.universal and from_state in {"PAUSED", "FAILED"} and hasattr(entity, "resume_to_state"):
        entity.resume_to_state = None
    entity.state = plan.target
    row = WorkflowTransition(
        entity_type=machine.entity_type,
        entity_id=entity_id,
        channel_id=channel.id if channel else None,
        from_state=from_state,
        to_state=plan.target,
        event=event,
        actor_type=actor.type,
        actor_id=actor.id,
        reason=reason,
        idempotency_key=key,
        occurred_at=now,
    )
    db.add(row)
    db.flush()
    details: dict[str, Any] = {"event": event}
    if plan.gate_auto:
        details["auto_rule_id"] = payload.get("auto_rule_id")
    if reason:
        details["reason"] = reason
    record(
        db,
        actor=actor,
        action=f"{machine.entity_type}.{event}",
        entity_type=machine.entity_type,
        entity_id=str(entity_id),
        channel_id=channel.id if channel else None,
        before={"state": from_state},
        after={"state": plan.target},
        details=details,
    )
    result = TransitionResult(entity_id, from_state, plan.target, event, False, row.id)
    for effect in ON_ENTER.get((machine.entity_type, plan.target), []):
        effect(db, machine, entity, result, actor)
    db.flush()
    return result


def move(
    db: Session,
    machine: Machine,
    entity: Any,
    to_state: str,
    *,
    actor: Actor,
    event_hint: str | None = None,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    reason: str | None = None,
) -> TransitionResult:
    """Transition by target state (for services that think in states, e.g. the upload runner).
    The unique edge from the current state to ``to_state`` is used; ``event_hint`` picks one if
    several exist."""
    candidates = [e for e in machine.edges_from(entity.state) if e.target == to_state]
    if event_hint is not None:
        candidates = [e for e in candidates if e.event == event_hint] or candidates
    if not candidates:
        raise TransitionRejected("INVALID_TRANSITION", [f"{entity.state} → {to_state} is not allowed."])
    return transition(
        db,
        machine,
        entity.id,
        candidates[0].event,
        actor=actor,
        payload=payload,
        idempotency_key=idempotency_key,
        reason=reason,
    )
