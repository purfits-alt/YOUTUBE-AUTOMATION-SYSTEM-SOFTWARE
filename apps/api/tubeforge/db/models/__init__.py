"""SQLAlchemy 2.0 models for the tables used so far (DATABASE_SCHEMA §1, §2 channels, §12).

The tables themselves are created by migration 0002 from the schema document; these models map
onto them (no create_all). tests/integration/test_models.py checks every mapped column exists in
the database with a compatible type and nullability.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, INET, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tubeforge.db.ids import uuid7


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {uuid.UUID: UUID(as_uuid=True), dict[str, Any]: JSONB}


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)


def _ts(nullable: bool = False) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=nullable)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _id()
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    totp_secret_enc: Mapped[bytes | None]
    totp_key_id: Mapped[str | None] = mapped_column(Text)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(Text, default="Asia/Karachi")
    locale: Mapped[str] = mapped_column(Text, default="en")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class Permission(Base):
    __tablename__ = "permissions"
    id: Mapped[uuid.UUID] = _id()
    code: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permissions.id"), primary_key=True)


class UserRole(Base):
    __tablename__ = "user_roles"
    # The table has a unique expression index instead of a PK; map (user_id, role_id) for the ORM.
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    channel_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("channels.id"))


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    mfa_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    reauth_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    last_seen_at: Mapped[datetime] = _ts()
    expires_at: Mapped[datetime] = _ts()
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)


class UserRecoveryCode(Base):
    __tablename__ = "user_recovery_codes"
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    code_hash: Mapped[str] = mapped_column(Text)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class SystemSettings(Base):
    __tablename__ = "system_settings"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    emergency_stop: Mapped[bool] = mapped_column(Boolean, default=False)
    emergency_stop_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    emergency_stop_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    emergency_stop_reason: Mapped[str | None] = mapped_column(Text)
    publishing_kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    night_render_start: Mapped[time] = mapped_column(Time)
    night_render_end: Mapped[time] = mapped_column(Time)
    quiet_hours_start: Mapped[time] = mapped_column(Time)
    quiet_hours_end: Mapped[time] = mapped_column(Time)
    owner_timezone: Mapped[str] = mapped_column(Text)
    disk_budget_gb: Mapped[int] = mapped_column(Integer)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class KillSwitch(Base):
    __tablename__ = "kill_switches"
    id: Mapped[uuid.UUID] = _id()
    scope: Mapped[str] = mapped_column(Text)
    target_id: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    reason: Mapped[str] = mapped_column(Text)
    set_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    cleared_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = _ts()
    actor_type: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str] = mapped_column(Text)
    channel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    before_sha256: Mapped[str | None] = mapped_column(String(64))
    after_sha256: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ip: Mapped[str | None] = mapped_column(INET)
    prev_hash: Mapped[str] = mapped_column(String(64))
    row_hash: Mapped[str] = mapped_column(String(64))


class SecurityEvent(Base):
    __tablename__ = "security_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    kind: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    channel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    youtube_channel_id: Mapped[str | None] = mapped_column(Text, unique=True)
    youtube_handle: Mapped[str | None] = mapped_column(Text)
    content_language: Mapped[str] = mapped_column(Text)
    audience_timezone: Mapped[str] = mapped_column(Text, default="UTC")
    operating_mode: Mapped[str] = mapped_column(Text, default="MANUAL")
    private_only_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    is_test_channel: Mapped[bool] = mapped_column(Boolean, default=False)
    is_monetised: Mapped[bool] = mapped_column(Boolean, default=True)
    local_only: Mapped[bool] = mapped_column(Boolean, default=False)
    successful_private_test_uploads: Mapped[int] = mapped_column(Integer, default=0)
    successful_private_test_runs: Mapped[int] = mapped_column(Integer, default=0)
    public_release_test_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    privacy_policy_url: Mapped[str | None] = mapped_column(Text)
    resume_to_state: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    method: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(Text)
    request_sha256: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    expires_at: Mapped[datetime] = _ts()


# --------------------------------------------------------------- Phase 4: channels, OAuth, YouTube
class ChannelPublishingRules(Base):
    __tablename__ = "channel_publishing_rules"
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id"), primary_key=True)
    max_long_per_day: Mapped[int] = mapped_column(Integer, default=1)
    max_long_per_week: Mapped[int] = mapped_column(Integer, default=7)
    max_shorts_per_day: Mapped[int] = mapped_column(Integer, default=2)
    min_originality_score: Mapped[Decimal] = mapped_column(Numeric(4, 1), default=Decimal(70))
    min_audit_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    allowed_topics: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    blocked_topics: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    block_high_inauthentic_risk_in_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    max_stock_runtime_share: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.60"))
    auto_publish_rules: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    auto_publish_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auto_publish_accepted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    required_private_test_runs: Mapped[int] = mapped_column(Integer, default=10)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class OnboardingStep(Base):
    __tablename__ = "onboarding_steps"
    id: Mapped[uuid.UUID] = _id()
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id"))
    step_code: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="TODO")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class OAuthClient(Base):
    __tablename__ = "oauth_clients"
    id: Mapped[uuid.UUID] = _id()
    label: Mapped[str] = mapped_column(Text)
    client_id: Mapped[str] = mapped_column(Text)
    client_secret_enc: Mapped[bytes | None]
    key_id: Mapped[str | None] = mapped_column(Text)
    gcp_project_id: Mapped[str | None] = mapped_column(Text)
    publishing_status: Mapped[str] = mapped_column(Text, default="TESTING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class OAuthConnection(Base):
    __tablename__ = "oauth_connections"
    id: Mapped[uuid.UUID] = _id()
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id"))
    oauth_client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("oauth_clients.id"))
    google_account_hint: Mapped[str | None] = mapped_column(Text)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text))
    refresh_token_enc: Mapped[bytes]
    key_id: Mapped[str] = mapped_column(Text)
    access_token_enc: Mapped[bytes | None]
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text)
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    refresh_expected_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorized_at: Mapped[datetime] = _ts()
    last_authorization_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class OAuthPendingFlow(Base):
    __tablename__ = "oauth_pending_flows"
    state: Mapped[str] = mapped_column(String(43), primary_key=True)
    code_verifier_enc: Mapped[bytes]
    key_id: Mapped[str] = mapped_column(Text)
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id"))
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    expires_at: Mapped[datetime] = _ts()


class VideoProject(Base):
    __tablename__ = "video_projects"
    id: Mapped[uuid.UUID] = _id()
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id"))
    idea_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    parent_project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    format: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    resume_to_state: Mapped[str | None] = mapped_column(Text)
    working_title: Mapped[str] = mapped_column(Text)
    packaging_promise: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    target_duration_s: Mapped[int] = mapped_column(Integer)
    render_profile: Mapped[dict[str, Any]] = mapped_column(JSONB)
    youtube_video_id: Mapped[str | None] = mapped_column(Text, unique=True)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MediaAsset(Base):
    __tablename__ = "media_assets"
    id: Mapped[uuid.UUID] = _id()
    channel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_s: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    origin: Mapped[str] = mapped_column(Text)
    retention_class: Mapped[str] = mapped_column(Text)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    quarantined: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_type: Mapped[str] = mapped_column(Text)
    created_by_id: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssetRights(Base):
    __tablename__ = "asset_rights"
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("media_assets.id"), primary_key=True)
    rights_basis: Mapped[str] = mapped_column(Text)
    licence_name: Mapped[str] = mapped_column(Text)
    licence_url: Mapped[str | None] = mapped_column(Text)
    commercial_use_allowed: Mapped[bool] = mapped_column(Boolean)
    editorial_only: Mapped[bool] = mapped_column(Boolean, default=False)
    attribution_required: Mapped[bool] = mapped_column(Boolean, default=False)
    lineage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    id: Mapped[uuid.UUID] = _id()
    channel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    subject_type: Mapped[str] = mapped_column(Text)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    subject_sha256: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(Text)
    requested_by_type: Mapped[str] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auto_rule_id: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    expires_at: Mapped[datetime] = _ts()


class UploadJob(Base):
    __tablename__ = "upload_jobs"
    id: Mapped[uuid.UUID] = _id()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("video_projects.id"))
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    approval_request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approval_requests.id"))
    file_asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("media_assets.id"))
    file_sha256: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(Text)
    privacy_status: Mapped[str] = mapped_column(Text)
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    made_for_kids: Mapped[bool] = mapped_column(Boolean)
    contains_synthetic_media: Mapped[bool] = mapped_column(Boolean)
    session_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    session_uri_enc: Mapped[bytes | None]
    key_id: Mapped[str | None] = mapped_column(Text)
    bytes_total: Mapped[int] = mapped_column(BigInteger)
    bytes_confirmed: Mapped[int] = mapped_column(BigInteger, default=0)
    youtube_video_id: Mapped[str | None] = mapped_column(Text)
    processing_status: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    error_class: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class QuotaLedger(Base):
    __tablename__ = "quota_ledger"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    pt_day: Mapped[date] = mapped_column(Date)
    gcp_project: Mapped[str] = mapped_column(Text)
    bucket: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(Text)
    units: Mapped[int] = mapped_column(Integer)
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    channel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    job_id: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)
    error_reason: Mapped[str | None] = mapped_column(Text)


class QuotaReservation(Base):
    __tablename__ = "quota_reservations"
    id: Mapped[uuid.UUID] = _id()
    gcp_project: Mapped[str] = mapped_column(Text)
    pt_day: Mapped[date] = mapped_column(Date)
    bucket: Mapped[str] = mapped_column(Text)
    units: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(Text)
    job_id: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    expires_at: Mapped[datetime] = _ts()


class QuotaConfig(Base):
    __tablename__ = "quota_config"
    gcp_project: Mapped[str] = mapped_column(Text, primary_key=True)
    bucket: Mapped[str] = mapped_column(Text, primary_key=True)
    daily_limit: Mapped[int] = mapped_column(Integer)
    reserve_pct: Mapped[int] = mapped_column(Integer, default=10)
    research_share_pct: Mapped[int] = mapped_column(Integer, default=30)
    method_costs: Mapped[dict[str, Any]] = mapped_column(JSONB)
    verified_at: Mapped[date] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(Text)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    channel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    dedup_key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DataDeletionTask(Base):
    __tablename__ = "data_deletion_tasks"
    id: Mapped[uuid.UUID] = _id()
    channel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[str] = mapped_column(Text)
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB)
    due_at: Mapped[datetime] = _ts()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class YoutubeApiCache(Base):
    __tablename__ = "youtube_api_cache"
    id: Mapped[uuid.UUID] = _id()
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    lookup_kind: Mapped[str] = mapped_column(Text)
    query_key: Mapped[str] = mapped_column(Text)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = _ts()
    expires_at: Mapped[datetime] = _ts()


class WorkflowTransition(Base):
    __tablename__ = "workflow_transitions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    channel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    from_state: Mapped[str] = mapped_column(Text)
    to_state: Mapped[str] = mapped_column(Text)
    event: Mapped[str] = mapped_column(Text)
    actor_type: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


# --------------------------------------------------------------- Phase 5: orchestrated entities
class VideoIdea(Base):
    __tablename__ = "video_ideas"
    id: Mapped[uuid.UUID] = _id()
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id"))
    state: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    angle: Mapped[str] = mapped_column(Text)
    target_viewer: Mapped[str | None] = mapped_column(Text)
    format: Mapped[str] = mapped_column(Text)
    pillar: Mapped[str | None] = mapped_column(Text)
    trend_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    originality_notes: Mapped[str | None] = mapped_column(Text)
    similarity_max: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    similar_to_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    calendar_date: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(Text)
    based_on_youtube_video_id: Mapped[str | None] = mapped_column(Text)
    variation_kind: Mapped[str | None] = mapped_column(Text)
    similarity_to_source: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RenderJob(Base):
    __tablename__ = "render_jobs"
    id: Mapped[uuid.UUID] = _id()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("video_projects.id"))
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    timeline_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    preset: Mapped[dict[str, Any]] = mapped_column(JSONB)
    segments_total: Mapped[int] = mapped_column(Integer, default=1)
    segments_done: Mapped[int] = mapped_column(Integer, default=0)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    output_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    qc_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_class: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)


class VoiceProfile(Base):
    __tablename__ = "voice_profiles"
    id: Mapped[uuid.UUID] = _id()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    label: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    engine: Mapped[str] = mapped_column(Text)
    sample_asset_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    embedding_enc: Mapped[bytes | None]
    key_id: Mapped[str | None] = mapped_column(Text)
    sample_seconds: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal(0))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StockPurchase(Base):
    __tablename__ = "stock_purchases"
    id: Mapped[uuid.UUID] = _id()
    channel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    provider_code: Mapped[str] = mapped_column(Text)
    provider_asset_id: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    licence_type: Mapped[str] = mapped_column(Text)
    price_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    quoted_at: Mapped[datetime] = _ts()
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_order_ref: Mapped[str | None] = mapped_column(Text)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    id: Mapped[uuid.UUID] = _id()
    notification_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("notifications.id"))
    channel: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_message_id: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --------------------------------------------------------------- Phase 5: AI Provider Gateway
class ProviderRegistry(Base):
    __tablename__ = "provider_registry"
    code: Mapped[str] = mapped_column(Text, primary_key=True)
    capability: Mapped[str] = mapped_column(Text)
    tier: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    paid_activation_step: Mapped[int] = mapped_column(Integer, default=0)
    licence: Mapped[str] = mapped_column(Text)
    licence_url: Mapped[str | None] = mapped_column(Text)
    lineage: Mapped[str | None] = mapped_column(Text)
    commercial_use: Mapped[str] = mapped_column(Text)
    data_use_training: Mapped[bool | None] = mapped_column(Boolean)
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    model_sha256: Mapped[str | None] = mapped_column(String(64))
    verified_at: Mapped[date] = mapped_column(Date)
    verified_url: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"
    provider_code: Mapped[str] = mapped_column(ForeignKey("provider_registry.code"), primary_key=True)
    secret_enc: Mapped[bytes]
    key_id: Mapped[str] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class UsageLimit(Base):
    __tablename__ = "usage_limits"
    id: Mapped[uuid.UUID] = _id()
    provider_code: Mapped[str] = mapped_column(ForeignKey("provider_registry.code"))
    scope: Mapped[str] = mapped_column(Text)
    scope_ref: Mapped[str | None] = mapped_column(Text)
    metric: Mapped[str] = mapped_column(Text)
    period: Mapped[str] = mapped_column(Text)
    limit_value: Mapped[int] = mapped_column(BigInteger)
    reset_tz: Mapped[str] = mapped_column(Text, default="America/Los_Angeles")


class UsageRecord(Base):
    __tablename__ = "usage_records"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    provider_code: Mapped[str] = mapped_column(Text)
    period_key: Mapped[str] = mapped_column(Text)
    metric: Mapped[str] = mapped_column(Text)
    amount: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(Text)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    channel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    task: Mapped[str | None] = mapped_column(Text)


class GatewayCache(Base):
    __tablename__ = "gateway_cache"
    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_code: Mapped[str] = mapped_column(Text)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    expires_at: Mapped[datetime] = _ts()
    hits: Mapped[int] = mapped_column(Integer, default=0)


class CostBudget(Base):
    __tablename__ = "cost_budgets"
    id: Mapped[uuid.UUID] = _id()
    scope: Mapped[str] = mapped_column(Text)
    provider_code: Mapped[str | None] = mapped_column(Text)
    month: Mapped[str] = mapped_column(String(7))
    cap_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    spent_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")


# --------------------------------------------------------------------- Phase 5: agents
class AgentConfiguration(Base):
    __tablename__ = "agent_configurations"
    agent_code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    is_auditor: Mapped[bool] = mapped_column(Boolean)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    prompt_version: Mapped[str] = mapped_column(Text)
    provider_chain: Mapped[list[str]] = mapped_column(JSONB)
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB)
    permissions: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[uuid.UUID] = _id()
    agent_code: Mapped[str] = mapped_column(ForeignKey("agent_configurations.agent_code"))
    channel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    job_id: Mapped[str | None] = mapped_column(Text)
    input_sha256: Mapped[str] = mapped_column(String(64))
    input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text)
    provider_code: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    repair_attempted: Mapped[bool] = mapped_column(Boolean, default=False)
    error_class: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    started_at: Mapped[datetime] = _ts()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


__all__ = [
    "AgentConfiguration",
    "AgentRun",
    "ApprovalRequest",
    "AssetRights",
    "AuditLog",
    "Base",
    "Channel",
    "ChannelPublishingRules",
    "CostBudget",
    "DataDeletionTask",
    "GatewayCache",
    "IdempotencyKey",
    "KillSwitch",
    "MediaAsset",
    "Notification",
    "NotificationDelivery",
    "OAuthClient",
    "OAuthConnection",
    "OAuthPendingFlow",
    "OnboardingStep",
    "Permission",
    "ProviderCredential",
    "ProviderRegistry",
    "QuotaConfig",
    "QuotaLedger",
    "QuotaReservation",
    "RenderJob",
    "Role",
    "RolePermission",
    "SecurityEvent",
    "Session",
    "StockPurchase",
    "SystemSettings",
    "UploadJob",
    "UsageLimit",
    "UsageRecord",
    "User",
    "UserRecoveryCode",
    "UserRole",
    "VideoIdea",
    "VideoProject",
    "VoiceProfile",
    "WorkflowTransition",
    "YoutubeApiCache",
]
