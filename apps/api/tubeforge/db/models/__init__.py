"""SQLAlchemy 2.0 models for the tables used so far (DATABASE_SCHEMA §1, §2 channels, §12).

The tables themselves are created by migration 0002 from the schema document; these models map
onto them (no create_all). tests/integration/test_models.py checks every mapped column exists in
the database with a compatible type and nullability.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import Any, ClassVar

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, Text, Time
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
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


__all__ = [
    "AuditLog",
    "Base",
    "Channel",
    "IdempotencyKey",
    "KillSwitch",
    "Permission",
    "Role",
    "RolePermission",
    "SecurityEvent",
    "Session",
    "SystemSettings",
    "User",
    "UserRecoveryCode",
    "UserRole",
]
