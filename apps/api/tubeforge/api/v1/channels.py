"""Channels, onboarding, modes, publishing rules and the private test upload (BACKEND_SPECIFICATION §2.3)."""

from __future__ import annotations

import hashlib
import json
import uuid
import zoneinfo
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from tubeforge import channel_lifecycle as lifecycle
from tubeforge.api.deps import Db, Principal, client_ip, request_id, require, require_recent_reauth
from tubeforge.api.errors import ProblemError, not_found, problem_doc
from tubeforge.api.idempotency import Idempotency
from tubeforge.api.pagination import Cursor, Limit, Page, clamp_limit
from tubeforge.audit import record, security_event
from tubeforge.db.ids import uuid7
from tubeforge.db.models import (
    Channel,
    ChannelPublishingRules,
    DataDeletionTask,
    OAuthClient,
    OnboardingStep,
    UploadJob,
)
from tubeforge.db.repository import VersionConflictError, update_versioned
from tubeforge.queue import defer_in_transaction
from tubeforge.secrets import SecretBox
from tubeforge.youtube import oauth, uploads
from tubeforge.youtube.client import PreflightRefused

router = APIRouter(tags=["channels"])

ChannelView = Annotated[Principal, Depends(require("channel.view"))]
ChannelManage = Annotated[Principal, Depends(require("channel.manage"))]
ChannelMode = Annotated[Principal, Depends(require("channel.mode"))]
UploadExecute = Annotated[Principal, Depends(require("upload.execute"))]
WRITE: dict[int | str, dict[str, Any]] = {
    409: problem_doc(
        "INVALID_TRANSITION / GUARDS_FAILED / CHANNEL_IN_USE / REFUSED_* (upload safety checks)"
    ),
    412: problem_doc("VERSION_CONFLICT: changed elsewhere (send the current version in If-Match)"),
    422: problem_doc("IDEMPOTENCY_MISMATCH: the key was used for a different request"),
    428: problem_doc("IF_MATCH_REQUIRED"),
}
Language = Literal["en", "es", "fr", "de", "ur"]
State = Literal[
    "PROPOSED",
    "APPROVED",
    "REJECTED",
    "ONBOARDING",
    "CONNECTED",
    "ACTIVE",
    "PAUSED",
    "NEEDS_REAUTH",
    "DISCONNECTING",
    "DISCONNECTED",
]
Mode = Literal["MANUAL", "SEMI_AUTOMATIC", "FULLY_AUTOMATIC"]
StepCode = Literal[
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
]
SYSTEM_STEPS = {"CONNECT", "TEST_UPLOAD"}  # set by TubeForge itself, not by hand
MIN_TEST_UPLOADS_FOR_PUBLIC = 3
NEVER_CONNECTED = {"PROPOSED", "APPROVED", "REJECTED", "DISCONNECTED"}


# ------------------------------------------------------------------------------------- schemas
class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    content_language: Language
    is_test_channel: bool = False
    is_monetised: bool = True


class ChannelPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    audience_timezone: str | None = Field(default=None, max_length=64)
    local_only: bool | None = None
    is_monetised: bool | None = None
    privacy_policy_url: str | None = Field(default=None, pattern=r"^https://[^\s]{3,490}$")

    @field_validator("audience_timezone")
    @classmethod
    def _tz(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                zoneinfo.ZoneInfo(value)
            except (zoneinfo.ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError("unknown time zone") from exc
        return value


class ChannelOut(BaseModel):
    id: uuid.UUID
    name: str
    state: State
    youtube_channel_id: str | None
    youtube_handle: str | None
    content_language: str
    audience_timezone: str
    operating_mode: Mode
    private_only_mode: bool
    is_test_channel: bool
    is_monetised: bool
    local_only: bool
    successful_private_test_uploads: int
    privacy_policy_url: str | None
    oauth_status: str
    oauth_expiring_soon: bool
    version: int
    created_at: datetime
    updated_at: datetime


class ModeIn(BaseModel):
    mode: Mode


class PrivateOnlyIn(BaseModel):
    enabled: bool


class RulesIn(BaseModel):
    max_long_per_day: int = Field(ge=0, le=10)
    max_long_per_week: int = Field(ge=0, le=50)
    max_shorts_per_day: int = Field(ge=0, le=20)
    min_originality_score: float = Field(ge=0, le=100)
    allowed_topics: list[str] = Field(default_factory=list, max_length=100)
    blocked_topics: list[str] = Field(default_factory=list, max_length=100)
    block_high_inauthentic_risk_in_manual: bool = False
    max_stock_runtime_share: float = Field(ge=0, le=1)
    auto_publish_rules: dict[str, Any] | None = None
    required_private_test_runs: int = Field(ge=1, le=100)


class RulesOut(RulesIn):
    channel_id: uuid.UUID
    auto_publish_rules_sha256: str | None
    auto_publish_accepted_at: datetime | None
    version: int


class AcceptRulesIn(BaseModel):
    rules_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class StepOut(BaseModel):
    step_code: StepCode
    status: Literal["TODO", "DONE", "SKIPPED"]
    completed_at: datetime | None
    notes: str | None
    system: bool


class StepPatch(BaseModel):
    status: Literal["TODO", "DONE", "SKIPPED"]
    notes: str | None = Field(default=None, max_length=1000)


class UploadJobOut(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    project_id: uuid.UUID
    state: str
    privacy_status: str
    made_for_kids: bool
    contains_synthetic_media: bool
    is_test: bool
    bytes_total: int
    bytes_confirmed: int
    youtube_video_id: str | None
    error_class: str | None
    error_detail: str | None
    created_at: datetime
    updated_at: datetime


class DeletionOut(BaseModel):
    id: uuid.UUID
    reason: str
    due_at: datetime


# ------------------------------------------------------------------------------------- helpers
def _box(request: Request) -> SecretBox:
    box: SecretBox = request.app.state.secret_box
    return box


def channel_out(db: Session, ch: Channel) -> ChannelOut:
    health = oauth.health(db, ch.id)
    return ChannelOut(
        id=ch.id,
        name=ch.name,
        state=ch.state,
        youtube_channel_id=ch.youtube_channel_id,
        youtube_handle=ch.youtube_handle,
        content_language=ch.content_language,
        audience_timezone=ch.audience_timezone,
        operating_mode=ch.operating_mode,
        private_only_mode=ch.private_only_mode,
        is_test_channel=ch.is_test_channel,
        is_monetised=ch.is_monetised,
        local_only=ch.local_only,
        successful_private_test_uploads=ch.successful_private_test_uploads,
        privacy_policy_url=ch.privacy_policy_url,
        oauth_status=health.status,
        oauth_expiring_soon=health.expiring_soon,
        version=ch.version,
        created_at=ch.created_at,
        updated_at=ch.updated_at,
    )


def upload_out(job: UploadJob) -> UploadJobOut:
    return UploadJobOut.model_validate(job, from_attributes=True)


def get_channel(db: Session, channel_id: uuid.UUID, *, lock: bool = False) -> Channel:
    channel = db.get(Channel, channel_id, with_for_update=lock)
    if channel is None or channel.deleted_at is not None:
        raise not_found("No such channel.")
    return channel


def if_match(value: str | None) -> int:
    if not value:
        raise ProblemError(428, "IF_MATCH_REQUIRED", "Version needed", 'Send If-Match, e.g. If-Match: "3".')
    try:
        return int(value.strip().removeprefix("W/").strip('"'))
    except ValueError as exc:
        raise ProblemError(
            400, "VALIDATION_ERROR", "Invalid request", "If-Match must be a version number."
        ) from exc


def _guards(failed: list[tuple[str, str, str | None]]) -> ProblemError:
    return ProblemError(
        409,
        "GUARDS_FAILED",
        "Not yet",
        "Some conditions are not met yet.",
        guards=[{"code": c, "message": m, "fix_href": h} for c, m, h in failed],
    )


def _transition(db: Session, channel: Channel, to: str, event: str, p: Principal, key: str) -> None:
    try:
        lifecycle.transition(db, channel, to, event=event, actor=p.actor, idempotency_key=key)
    except lifecycle.TransitionError as exc:
        raise ProblemError(
            409, "INVALID_TRANSITION", "Not possible now", f"A {exc.from_state} channel cannot do this."
        ) from exc


def _audit(
    request: Request, db: Session, p: Principal, action: str, channel: Channel, **details: Any
) -> None:
    record(
        db,
        actor=p.actor,
        action=action,
        entity_type="channel",
        entity_id=str(channel.id),
        channel_id=channel.id,
        details=details or None,
        request_id=request_id(request),
        ip=client_ip(request),
    )


def _rules(db: Session, channel: Channel) -> ChannelPublishingRules:
    rules = db.get(ChannelPublishingRules, channel.id)
    if rules is None:
        rules = ChannelPublishingRules(channel_id=channel.id)
        db.add(rules)
        db.flush()
        db.refresh(rules)
    return rules


def rules_sha256(rules: dict[str, Any] | None) -> str | None:
    if rules is None:
        return None
    return hashlib.sha256(json.dumps(rules, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _rules_out(r: ChannelPublishingRules) -> RulesOut:
    return RulesOut(
        channel_id=r.channel_id,
        max_long_per_day=r.max_long_per_day,
        max_long_per_week=r.max_long_per_week,
        max_shorts_per_day=r.max_shorts_per_day,
        min_originality_score=float(r.min_originality_score),
        allowed_topics=list(r.allowed_topics),
        blocked_topics=list(r.blocked_topics),
        block_high_inauthentic_risk_in_manual=r.block_high_inauthentic_risk_in_manual,
        max_stock_runtime_share=float(r.max_stock_runtime_share),
        auto_publish_rules=r.auto_publish_rules,
        required_private_test_runs=r.required_private_test_runs,
        auto_publish_rules_sha256=rules_sha256(r.auto_publish_rules),
        auto_publish_accepted_at=r.auto_publish_accepted_at,
        version=r.version,
    )


# --------------------------------------------------------------------------------------- CRUD
@router.get("/channels", response_model=Page[ChannelOut])
def list_channels(
    db: Db,
    _: ChannelView,
    limit: Limit = None,
    cursor: Cursor = None,
    state: State | None = None,
    language: Language | None = None,
    mode: Mode | None = None,
) -> Page[ChannelOut]:
    n = clamp_limit(limit)
    stmt = select(Channel).where(Channel.deleted_at.is_(None)).order_by(Channel.id.desc()).limit(n + 1)
    if state:
        stmt = stmt.where(Channel.state == state)
    if language:
        stmt = stmt.where(Channel.content_language == language)
    if mode:
        stmt = stmt.where(Channel.operating_mode == mode)
    after = uuid_cursor(cursor)
    if after is not None:
        stmt = stmt.where(Channel.id < after)
    rows = list(db.scalars(stmt))
    more = len(rows) > n
    rows = rows[:n]
    return Page[ChannelOut](
        items=[channel_out(db, r) for r in rows],
        next_cursor=f"c{rows[-1].id.int}" if more and rows else None,
    )


def uuid_cursor(cursor: str | None) -> uuid.UUID | None:
    """Cursors are ``c<digits>``; for uuid7 tables the digits are the UUID as an integer."""
    if not cursor:
        return None
    try:
        return uuid.UUID(int=int(cursor.removeprefix("c")))
    except ValueError as exc:
        raise ProblemError(400, "VALIDATION_ERROR", "Invalid request", "Bad cursor.") from exc


@router.post("/channels", response_model=ChannelOut, status_code=201, responses=WRITE)
def create_channel(body: ChannelCreate, request: Request, db: Db, p: ChannelManage) -> Any:
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    channel = Channel(id=uuid7(), state="APPROVED", **body.model_dump())
    db.add(channel)
    db.flush()
    db.add(ChannelPublishingRules(channel_id=channel.id))
    db.flush()
    db.refresh(channel)
    _audit(request, db, p, "channel.created", channel, name=channel.name)
    out = channel_out(db, channel)
    idem.store(201, out.model_dump(mode="json"))
    db.commit()
    return out


@router.get("/channels/{channel_id}", response_model=ChannelOut)
def read_channel(channel_id: uuid.UUID, db: Db, _: ChannelView, response: Response) -> ChannelOut:
    channel = get_channel(db, channel_id)
    response.headers["ETag"] = f'"{channel.version}"'
    return channel_out(db, channel)


@router.patch("/channels/{channel_id}", response_model=ChannelOut, responses=WRITE)
def patch_channel(
    channel_id: uuid.UUID,
    body: ChannelPatch,
    request: Request,
    db: Db,
    p: ChannelManage,
    if_match_header: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ChannelOut:
    expected = if_match(if_match_header)
    channel = get_channel(db, channel_id)
    values = body.model_dump(exclude_unset=True)
    try:
        update_versioned(db, Channel, channel_id, expected, values)
    except VersionConflictError as exc:
        raise ProblemError(
            412, "VERSION_CONFLICT", "Changed elsewhere", "Reload and try again.", current_version=exc.current
        ) from exc
    db.refresh(channel)
    if values.get("privacy_policy_url"):
        lifecycle.mark_step(db, channel.id, "PRIVACY_POLICY")
        lifecycle.maybe_activate(db, channel, actor=p.actor)
    _audit(request, db, p, "channel.updated", channel, fields=sorted(values))
    db.commit()
    return channel_out(db, channel)


@router.delete("/channels/{channel_id}", status_code=204, responses=WRITE)
def delete_channel(channel_id: uuid.UUID, request: Request, db: Db, p: ChannelManage) -> Response:
    require_recent_reauth(p)
    channel = get_channel(db, channel_id, lock=True)
    never = channel.state == "ONBOARDING" and oauth.current_connection(db, channel.id) is None
    if channel.state not in NEVER_CONNECTED and not never:
        raise ProblemError(
            409, "CHANNEL_IN_USE", "Disconnect first", "Disconnect this channel from YouTube first."
        )
    channel.deleted_at = datetime.now(UTC)
    _audit(request, db, p, "channel.deleted", channel)
    security_event(db, "CHANNEL_DELETED", "WARNING", user_id=p.user.id, channel_id=channel.id)
    db.commit()
    return Response(status_code=204)


# ----------------------------------------------------------------------------------- commands
Command = Literal["start-onboarding", "pause", "resume", "disconnect", "reconnect"]


@router.post("/channels/{channel_id}/commands/{cmd}", response_model=ChannelOut, responses=WRITE)
def command(channel_id: uuid.UUID, cmd: Command, request: Request, db: Db, p: ChannelManage) -> Any:
    if cmd == "disconnect":
        require_recent_reauth(p)  # revokes Google access and schedules deletion: confirm it's you
    idem = Idempotency(db, request, p.user.id, {"cmd": cmd, "channel": str(channel_id)})
    if (replayed := idem.replay()) is not None:
        return replayed
    channel = get_channel(db, channel_id, lock=True)
    key = str(idem.key)
    if cmd == "start-onboarding":
        _transition(db, channel, "ONBOARDING", "start_onboarding", p, key)
        lifecycle.ensure_onboarding_steps(db, channel)
        if db.scalar(select(OAuthClient.id).limit(1)) is not None:
            lifecycle.mark_step(db, channel.id, "OAUTH_CLIENT")
        if channel.privacy_policy_url:
            lifecycle.mark_step(db, channel.id, "PRIVACY_POLICY")
    elif cmd == "pause":
        previous = channel.state
        _transition(db, channel, "PAUSED", "pause", p, key)
        channel.resume_to_state = previous
    elif cmd == "resume":
        if channel.state != "PAUSED":
            raise ProblemError(409, "INVALID_TRANSITION", "Not paused", "Only a paused channel can resume.")
        conn = oauth.current_connection(db, channel.id)
        if conn is None or conn.status != "ACTIVE":
            raise _guards(
                [
                    (
                        "OAUTH",
                        "The YouTube connection needs to be renewed.",
                        f"/channels/{channel.id}/onboarding",
                    )
                ]
            )
        target = channel.resume_to_state if channel.resume_to_state in {"CONNECTED", "ACTIVE"} else "ACTIVE"
        channel.resume_to_state = None
        _transition(db, channel, target, "resume", p, key)
    elif cmd == "disconnect":
        try:
            oauth.disconnect(db, _box(request), request.app.state.google_oauth, channel, actor=p.actor)
        except oauth.OAuthFlowError as exc:
            raise ProblemError(409, "INVALID_TRANSITION", "Not possible now", exc.message) from exc
    else:  # reconnect
        _transition(db, channel, "ONBOARDING", "reconnect", p, key)
        lifecycle.ensure_onboarding_steps(db, channel)
        lifecycle.reset_connection_steps(db, channel)
    db.flush()
    db.refresh(channel)
    out = channel_out(db, channel)
    idem.store(200, out.model_dump(mode="json"))
    db.commit()
    return out


# ------------------------------------------------------------------------------- mode / private
@router.post("/channels/{channel_id}/mode", response_model=ChannelOut, responses=WRITE)
def set_mode(channel_id: uuid.UUID, body: ModeIn, request: Request, db: Db, p: ChannelMode) -> Any:
    require_recent_reauth(p)
    idem = Idempotency(db, request, p.user.id, {"mode": body.mode, "channel": str(channel_id)})
    if (replayed := idem.replay()) is not None:
        return replayed
    channel = get_channel(db, channel_id, lock=True)
    if body.mode == "FULLY_AUTOMATIC":
        rules = _rules(db, channel)
        failed: list[tuple[str, str, str | None]] = []
        if channel.successful_private_test_runs < rules.required_private_test_runs:
            failed.append(
                (
                    "TEST_RUNS",
                    f"{channel.successful_private_test_runs} of {rules.required_private_test_runs}"
                    " private test runs done.",
                    None,
                )
            )
        if not channel.public_release_test_passed:
            failed.append(("PUBLIC_RELEASE_TEST", "The public-release test has not passed yet.", None))
        if rules.auto_publish_accepted_at is None:
            failed.append(
                ("AUTO_RULES", "Accept the auto-publish rules first.", f"/channels/{channel.id}/settings")
            )
        if failed:
            raise _guards(failed)
    before = channel.operating_mode
    channel.operating_mode = body.mode
    _audit(request, db, p, "channel.mode_changed", channel, before=before, after=body.mode)
    security_event(
        db,
        "CHANNEL_MODE_CHANGED",
        "WARNING",
        user_id=p.user.id,
        channel_id=channel.id,
        details={"mode": body.mode},
    )
    db.flush()
    db.refresh(channel)
    out = channel_out(db, channel)
    idem.store(200, out.model_dump(mode="json"))
    db.commit()
    return out


@router.post("/channels/{channel_id}/private-only", response_model=ChannelOut, responses=WRITE)
def set_private_only(
    channel_id: uuid.UUID, body: PrivateOnlyIn, request: Request, db: Db, p: ChannelMode
) -> Any:
    require_recent_reauth(p)
    idem = Idempotency(db, request, p.user.id, {"enabled": body.enabled, "channel": str(channel_id)})
    if (replayed := idem.replay()) is not None:
        return replayed
    channel = get_channel(db, channel_id, lock=True)
    if not body.enabled and channel.successful_private_test_uploads < MIN_TEST_UPLOADS_FOR_PUBLIC:
        raise _guards(
            [
                (
                    "TEST_UPLOADS",
                    f"{channel.successful_private_test_uploads} of {MIN_TEST_UPLOADS_FOR_PUBLIC}"
                    " private test uploads done.",
                    f"/channels/{channel.id}",
                )
            ]
        )
    before = channel.private_only_mode
    channel.private_only_mode = body.enabled
    _audit(request, db, p, "channel.private_only_changed", channel, before=before, after=body.enabled)
    security_event(
        db,
        "PRIVATE_ONLY_CHANGED",
        "INFO" if body.enabled else "WARNING",
        user_id=p.user.id,
        channel_id=channel.id,
        details={"enabled": body.enabled},
    )
    db.flush()
    db.refresh(channel)
    out = channel_out(db, channel)
    idem.store(200, out.model_dump(mode="json"))
    db.commit()
    return out


# ------------------------------------------------------------------------------ publishing rules
@router.get("/channels/{channel_id}/publishing-rules", response_model=RulesOut)
def get_rules(channel_id: uuid.UUID, db: Db, _: ChannelView, response: Response) -> RulesOut:
    rules = _rules(db, get_channel(db, channel_id))
    db.commit()
    response.headers["ETag"] = f'"{rules.version}"'
    return _rules_out(rules)


@router.put("/channels/{channel_id}/publishing-rules", response_model=RulesOut, responses=WRITE)
def put_rules(
    channel_id: uuid.UUID,
    body: RulesIn,
    request: Request,
    db: Db,
    p: ChannelManage,
    if_match_header: Annotated[str | None, Header(alias="If-Match")] = None,
) -> RulesOut:
    expected = if_match(if_match_header)
    channel = get_channel(db, channel_id)
    rules = _rules(db, channel)
    values = body.model_dump()
    values["min_originality_score"] = Decimal(str(body.min_originality_score))
    values["max_stock_runtime_share"] = Decimal(str(body.max_stock_runtime_share))
    if rules_sha256(body.auto_publish_rules) != rules_sha256(rules.auto_publish_rules):
        values["auto_publish_accepted_at"] = None  # changed rules need a new acceptance (DP-6)
        values["auto_publish_accepted_by"] = None
    R = ChannelPublishingRules  # noqa: N806
    result = db.execute(
        update(R)
        .where(R.channel_id == channel.id, R.version == expected)
        .values(**values, version=expected + 1)
        .returning(R.version)
    ).scalar_one_or_none()
    if result is None:
        raise ProblemError(
            412,
            "VERSION_CONFLICT",
            "Changed elsewhere",
            "Reload and try again.",
            current_version=rules.version,
        )
    db.refresh(rules)
    _audit(request, db, p, "channel.publishing_rules_updated", channel)
    db.commit()
    return _rules_out(rules)


@router.post(
    "/channels/{channel_id}/publishing-rules/accept-auto-rules", response_model=RulesOut, responses=WRITE
)
def accept_auto_rules(
    channel_id: uuid.UUID, body: AcceptRulesIn, request: Request, db: Db, p: ChannelMode
) -> Any:
    require_recent_reauth(p)
    idem = Idempotency(db, request, p.user.id, {"sha": body.rules_sha256, "channel": str(channel_id)})
    if (replayed := idem.replay()) is not None:
        return replayed
    channel = get_channel(db, channel_id)
    rules = _rules(db, channel)
    current = rules_sha256(rules.auto_publish_rules)
    if current is None or current != body.rules_sha256:
        raise ProblemError(
            409, "RULES_CHANGED", "Rules changed", "The rules you accepted are not the current ones. Reload."
        )
    rules.auto_publish_accepted_at = datetime.now(UTC)
    rules.auto_publish_accepted_by = p.user.id
    _audit(request, db, p, "channel.auto_rules_accepted", channel, rules_sha256=current)
    security_event(db, "AUTO_RULES_ACCEPTED", "WARNING", user_id=p.user.id, channel_id=channel.id)
    db.flush()
    out = _rules_out(rules)
    idem.store(200, out.model_dump(mode="json"))
    db.commit()
    return out


# ---------------------------------------------------------------------------------- onboarding
def _step_out(s: OnboardingStep) -> StepOut:
    return StepOut(
        step_code=s.step_code,
        status=s.status,
        completed_at=s.completed_at,
        notes=s.notes,
        system=s.step_code in SYSTEM_STEPS,
    )


@router.get("/channels/{channel_id}/onboarding", response_model=list[StepOut])
def onboarding(channel_id: uuid.UUID, db: Db, _: ChannelView) -> list[StepOut]:
    channel = get_channel(db, channel_id)
    steps = lifecycle.ensure_onboarding_steps(db, channel)
    db.commit()
    return [_step_out(s) for s in steps]


@router.patch("/channels/{channel_id}/onboarding/{step_code}", response_model=StepOut, responses=WRITE)
def patch_step(
    channel_id: uuid.UUID, step_code: StepCode, body: StepPatch, request: Request, db: Db, p: ChannelManage
) -> StepOut:
    channel = get_channel(db, channel_id)
    if step_code in SYSTEM_STEPS:
        raise ProblemError(409, "SYSTEM_STEP", "Done by TubeForge", "This step completes by itself.")
    lifecycle.ensure_onboarding_steps(db, channel)
    step = db.scalars(
        select(OnboardingStep).where(
            OnboardingStep.channel_id == channel.id, OnboardingStep.step_code == step_code
        )
    ).one()
    step.status = body.status
    step.completed_at = datetime.now(UTC) if body.status == "DONE" else None
    if body.notes is not None:
        step.notes = body.notes
    _audit(request, db, p, "channel.onboarding_step", channel, step=step_code, status=body.status)
    db.commit()
    return _step_out(step)


# ----------------------------------------------------------------------------- uploads / data
@router.post(
    "/channels/{channel_id}/test-upload", response_model=UploadJobOut, status_code=202, responses=WRITE
)
def test_upload(channel_id: uuid.UUID, request: Request, db: Db, p: UploadExecute) -> Any:
    idem = Idempotency(db, request, p.user.id, {"channel": str(channel_id)})
    if (replayed := idem.replay()) is not None:
        return replayed
    channel = get_channel(db, channel_id, lock=True)
    try:
        job = uploads.create_test_upload(db, channel=channel, owner=p.actor, owner_id=p.user.id)
    except PreflightRefused as exc:
        db.commit()  # keep the refusal's audit row, security event and notification
        status = 503 if exc.code == "WAITING_QUOTA" else 409
        raise ProblemError(status, exc.code, "Upload stopped by a safety check", exc.message) from exc
    except oauth.OAuthFlowError as exc:
        raise ProblemError(409, exc.code, "YouTube connection", exc.message) from exc
    defer_in_transaction(
        db,
        "yt.upload",
        queue="youtube",
        args={"upload_job_id": str(job.id)},
        queueing_lock=f"upload-job:{job.id}",
        lock=f"upload-channel:{channel.id}",  # one upload per channel at a time
    )
    db.flush()
    db.refresh(job)
    out = upload_out(job)
    idem.store(202, out.model_dump(mode="json"))
    db.commit()
    return out


@router.post(
    "/channels/{channel_id}/delete-api-data", response_model=DeletionOut, status_code=202, responses=WRITE
)
def delete_api_data(channel_id: uuid.UUID, request: Request, db: Db, p: ChannelManage) -> Any:
    require_recent_reauth(p)
    idem = Idempotency(db, request, p.user.id, {"channel": str(channel_id)})
    if (replayed := idem.replay()) is not None:
        return replayed
    channel = get_channel(db, channel_id)
    task = DataDeletionTask(
        id=uuid7(),
        channel_id=channel.id,
        reason="OWNER_REQUEST",
        scope={"tables": ["analytics_snapshots", "comment_suggestions"]},
        due_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(task)
    _audit(request, db, p, "channel.api_data_deletion_requested", channel)
    db.flush()
    out = DeletionOut(id=task.id, reason=task.reason, due_at=task.due_at)
    idem.store(202, out.model_dump(mode="json"))
    db.commit()
    return out
