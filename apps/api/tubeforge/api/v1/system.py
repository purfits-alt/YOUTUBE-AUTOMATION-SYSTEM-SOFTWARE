"""System controls & settings (BACKEND_SPECIFICATION §4.2).

Emergency Stop and kill switches only record and broadcast the state in Phase 3; the orchestrator
and workers check them from Phase 5 (they must never be bypassed — CLAUDE.md).
"""

from __future__ import annotations

import uuid
import zoneinfo
from datetime import UTC, datetime, time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.api.deps import Db, Principal, client_ip, request_id, require, require_recent_reauth
from tubeforge.api.errors import ProblemError, not_found, problem_doc
from tubeforge.api.idempotency import Idempotency
from tubeforge.audit import record, security_event
from tubeforge.db.models import KillSwitch, SystemSettings
from tubeforge.db.repository import VersionConflictError, update_versioned

router = APIRouter(tags=["system"])

IDEMPOTENT: dict[int | str, dict[str, Any]] = {
    422: problem_doc("IDEMPOTENCY_MISMATCH: the key was used for a different request")
}


class EmergencyStopOut(BaseModel):
    active: bool
    reason: str | None
    since: datetime | None
    by: uuid.UUID | None


class KillSwitchOut(BaseModel):
    id: uuid.UUID
    scope: Literal["CHANNEL", "AGENT", "PROVIDER", "PUBLISHING_CHANNEL"]
    target_id: str
    active: bool
    reason: str
    set_at: datetime


class ControlsOut(BaseModel):
    emergency_stop: EmergencyStopOut
    publishing_kill_switch: bool
    kill_switches: list[KillSwitchOut]


class ReasonIn(BaseModel):
    reason: str = Field(default="", max_length=500)


class PublishingSwitchIn(BaseModel):
    active: bool
    reason: str = Field(min_length=3, max_length=500)


class KillSwitchIn(BaseModel):
    scope: Literal["CHANNEL", "AGENT", "PROVIDER", "PUBLISHING_CHANNEL"]
    target_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=3, max_length=500)


# Local wall-clock times in the owner's time zone, as "HH:MM" (JSON-Schema "time" would need an offset).
HHMM = Annotated[str, Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$", examples=["01:00"])]


def _hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def _parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


class SettingsOut(BaseModel):
    night_render_start: HHMM
    night_render_end: HHMM
    quiet_hours_start: HHMM
    quiet_hours_end: HHMM
    owner_timezone: str
    disk_budget_gb: int
    settings: dict[str, Any]
    version: int
    updated_at: datetime


class SettingsIn(BaseModel):
    night_render_start: HHMM
    night_render_end: HHMM
    quiet_hours_start: HHMM
    quiet_hours_end: HHMM
    owner_timezone: str = Field(max_length=64)
    disk_budget_gb: int = Field(ge=10, le=100_000)
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("owner_timezone")
    @classmethod
    def _valid_tz(cls, value: str) -> str:
        try:
            zoneinfo.ZoneInfo(value)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("unknown time zone (use an IANA name such as Asia/Karachi)") from exc
        return value


def _settings_row(db: Session) -> SystemSettings:
    row = db.get(SystemSettings, 1)
    if row is None:
        raise ProblemError(503, "NOT_READY", "Not ready", "Settings row missing: run 'tubeforge-db upgrade'.")
    return row


def controls_snapshot(db: Session) -> ControlsOut:
    s = _settings_row(db)
    switches = db.scalars(select(KillSwitch).where(KillSwitch.active.is_(True)).order_by(KillSwitch.set_at))
    return ControlsOut(
        emergency_stop=EmergencyStopOut(
            active=s.emergency_stop,
            reason=s.emergency_stop_reason,
            since=s.emergency_stop_at,
            by=s.emergency_stop_by,
        ),
        publishing_kill_switch=s.publishing_kill_switch,
        kill_switches=[KillSwitchOut.model_validate(k, from_attributes=True) for k in switches],
    )


def _broadcast(request: Request, controls: ControlsOut) -> None:
    request.app.state.events.publish("control.changed", controls.model_dump(mode="json"))


def _audit(
    request: Request,
    db: Session,
    p: Principal,
    action: str,
    entity_type: str,
    entity_id: str,
    before: Any,
    after: Any,
    **details: Any,
) -> None:
    record(
        db,
        actor=p.actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        details=details,
        request_id=request_id(request),
        ip=client_ip(request),
    )


@router.get("/system/controls", response_model=ControlsOut)
def get_controls(db: Db, _: Annotated[Principal, Depends(require("dashboard.view"))]) -> ControlsOut:
    return controls_snapshot(db)


@router.post("/system/emergency-stop", response_model=ControlsOut, responses=IDEMPOTENT)
def emergency_stop(
    body: ReasonIn, request: Request, db: Db, p: Annotated[Principal, Depends(require("emergency.activate"))]
) -> Any:
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    s = _settings_row(db)
    before = controls_snapshot(db).model_dump(mode="json")
    if not s.emergency_stop:
        s.emergency_stop, s.emergency_stop_at, s.emergency_stop_by = True, datetime.now(UTC), p.user.id
        s.emergency_stop_reason = body.reason.strip() or None
        security_event(db, "EMERGENCY_STOP", "CRITICAL", user_id=p.user.id, details={"reason": body.reason})
    db.flush()
    after = controls_snapshot(db)
    _audit(
        request,
        db,
        p,
        "system.emergency_stop",
        "system_settings",
        "1",
        before,
        after.model_dump(mode="json"),
        reason=body.reason,
    )
    idem.store(200, after.model_dump(mode="json"))
    db.commit()
    _broadcast(request, after)
    return after


@router.post("/system/emergency-stop/clear", response_model=ControlsOut, responses=IDEMPOTENT)
def emergency_stop_clear(
    body: ReasonIn, request: Request, db: Db, p: Annotated[Principal, Depends(require("emergency.clear"))]
) -> Any:
    require_recent_reauth(p)
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    s = _settings_row(db)
    before = controls_snapshot(db).model_dump(mode="json")
    s.emergency_stop, s.emergency_stop_at, s.emergency_stop_by, s.emergency_stop_reason = (
        False,
        None,
        None,
        None,
    )
    security_event(
        db, "EMERGENCY_STOP_CLEARED", "WARNING", user_id=p.user.id, details={"reason": body.reason}
    )
    db.flush()
    after = controls_snapshot(db)
    _audit(
        request,
        db,
        p,
        "system.emergency_stop_clear",
        "system_settings",
        "1",
        before,
        after.model_dump(mode="json"),
        reason=body.reason,
    )
    idem.store(200, after.model_dump(mode="json"))
    db.commit()
    _broadcast(request, after)
    return after


@router.post("/system/publishing-kill-switch", response_model=ControlsOut, responses=IDEMPOTENT)
def publishing_kill_switch(
    body: PublishingSwitchIn,
    request: Request,
    db: Db,
    p: Annotated[Principal, Depends(require("publishing.control"))],
) -> Any:
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    s = _settings_row(db)
    before = controls_snapshot(db).model_dump(mode="json")
    s.publishing_kill_switch = body.active
    security_event(
        db,
        "KILL_SWITCH",
        "WARNING",
        user_id=p.user.id,
        details={"scope": "PUBLISHING", "active": body.active, "reason": body.reason},
    )
    db.flush()
    after = controls_snapshot(db)
    _audit(
        request,
        db,
        p,
        "system.publishing_kill_switch",
        "system_settings",
        "1",
        before,
        after.model_dump(mode="json"),
        reason=body.reason,
    )
    idem.store(200, after.model_dump(mode="json"))
    db.commit()
    _broadcast(request, after)
    return after


@router.post("/system/kill-switches", response_model=KillSwitchOut, responses=IDEMPOTENT)
def set_kill_switch(
    body: KillSwitchIn, request: Request, db: Db, p: Annotated[Principal, Depends(require("controls.manage"))]
) -> Any:
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    row = db.scalar(
        select(KillSwitch).where(KillSwitch.scope == body.scope, KillSwitch.target_id == body.target_id)
    )
    if row is None:
        row = KillSwitch(scope=body.scope, target_id=body.target_id, reason=body.reason, set_by=p.user.id)
        db.add(row)
    else:
        row.active, row.reason, row.set_by, row.set_at = True, body.reason, p.user.id, datetime.now(UTC)
        row.cleared_by = row.cleared_at = None
    security_event(
        db,
        "KILL_SWITCH",
        "WARNING",
        user_id=p.user.id,
        details={"scope": body.scope, "target": body.target_id, "active": True},
    )
    db.flush()
    out = KillSwitchOut.model_validate(row, from_attributes=True)
    _audit(
        request,
        db,
        p,
        "system.kill_switch_set",
        "kill_switch",
        str(row.id),
        None,
        out.model_dump(mode="json"),
    )
    idem.store(200, out.model_dump(mode="json"))
    db.commit()
    _broadcast(request, controls_snapshot(db))
    return out


@router.delete("/system/kill-switches/{switch_id}", status_code=204)
def clear_kill_switch(
    switch_id: uuid.UUID,
    request: Request,
    db: Db,
    p: Annotated[Principal, Depends(require("controls.manage"))],
) -> None:
    row = db.get(KillSwitch, switch_id)
    if row is None or not row.active:
        raise not_found("Kill switch not found or already cleared.")
    row.active, row.cleared_by, row.cleared_at = False, p.user.id, datetime.now(UTC)
    security_event(
        db,
        "KILL_SWITCH",
        "INFO",
        user_id=p.user.id,
        details={"scope": row.scope, "target": row.target_id, "active": False},
    )
    _audit(
        request,
        db,
        p,
        "system.kill_switch_clear",
        "kill_switch",
        str(row.id),
        {"active": True},
        {"active": False},
    )
    db.commit()
    _broadcast(request, controls_snapshot(db))


def _settings_out(row: SystemSettings) -> SettingsOut:
    return SettingsOut(
        night_render_start=_hhmm(row.night_render_start),
        night_render_end=_hhmm(row.night_render_end),
        quiet_hours_start=_hhmm(row.quiet_hours_start),
        quiet_hours_end=_hhmm(row.quiet_hours_end),
        owner_timezone=row.owner_timezone,
        disk_budget_gb=row.disk_budget_gb,
        settings=row.settings,
        version=row.version,
        updated_at=row.updated_at,
    )


@router.get("/settings", response_model=SettingsOut)
def get_settings_route(
    response: Response, db: Db, _: Annotated[Principal, Depends(require("settings.manage"))]
) -> SettingsOut:
    row = _settings_row(db)
    response.headers["ETag"] = f'"{row.version}"'
    return _settings_out(row)


@router.put(
    "/settings",
    response_model=SettingsOut,
    responses={
        412: problem_doc("VERSION_CONFLICT (body has current_version)"),
        428: problem_doc("IF_MATCH_REQUIRED"),
    },
)
def put_settings(
    body: SettingsIn,
    request: Request,
    db: Db,
    p: Annotated[Principal, Depends(require("settings.manage"))],
    if_match: Annotated[str | None, Header()] = None,
) -> Any:
    if not if_match:
        raise ProblemError(
            428,
            "IF_MATCH_REQUIRED",
            "Version needed",
            'Send If-Match with the version you edited, e.g. If-Match: "3".',
        )
    try:
        expected = int(if_match.strip().strip('"').removeprefix("W/").strip('"'))
    except ValueError as exc:
        raise ProblemError(
            400, "VALIDATION_ERROR", "Invalid request", "If-Match must be a version number."
        ) from exc
    before = _settings_out(_settings_row(db)).model_dump(mode="json")
    try:
        values = body.model_dump()
        for key in ("night_render_start", "night_render_end", "quiet_hours_start", "quiet_hours_end"):
            values[key] = _parse_hhmm(values[key])
        update_versioned(db, SystemSettings, 1, expected, values)
    except VersionConflictError as exc:
        raise ProblemError(
            412,
            "VERSION_CONFLICT",
            "Changed elsewhere",
            "Settings were changed in another window. Reload and try again.",
            current_version=exc.current,
        ) from exc
    db.expire_all()
    after = _settings_out(_settings_row(db))
    _audit(request, db, p, "settings.update", "system_settings", "1", before, after.model_dump(mode="json"))
    db.commit()
    return JSONResponse(after.model_dump(mode="json"), headers={"ETag": f'"{after.version}"'})
