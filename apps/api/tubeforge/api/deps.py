"""Request dependencies: DB session, authenticated principal, CSRF, permissions, step-up.

Every /api/v1 route must declare its access rule with exactly one of ``Depends(public)``,
``Depends(authenticated)`` / ``Depends(pre_mfa)`` or ``Depends(require("perm.code"))``.
tests/unit/test_route_permissions.py fails the build if a route has none.
"""

from __future__ import annotations

import ipaddress
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.api.errors import ProblemError, forbidden, unauthenticated
from tubeforge.audit import Actor, security_event
from tubeforge.auth.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, csrf_matches, unsign_session
from tubeforge.db.models import Permission, Role, RolePermission, User, UserRole
from tubeforge.db.models import Session as SessionRow

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
IDLE_TIMEOUT = timedelta(hours=8)
ABSOLUTE_TIMEOUT = timedelta(days=7)
REAUTH_WINDOW = timedelta(minutes=5)
TOUCH_EVERY = timedelta(seconds=60)


def get_db(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    db = factory()
    try:
        yield db
    finally:
        db.rollback()  # anything not explicitly committed by the route is discarded
        db.close()


Db = Annotated[Session, Depends(get_db)]


@dataclass
class Principal:
    user: User
    session: SessionRow
    roles: frozenset[str]
    permissions: frozenset[str]

    @property
    def actor(self) -> Actor:
        return Actor("OWNER" if "OWNER" in self.roles else "USER", str(self.user.id))

    def has(self, permission: str) -> bool:
        return permission in self.permissions


def load_permissions(db: Session, user_id: uuid.UUID) -> tuple[frozenset[str], frozenset[str]]:
    roles = frozenset(
        db.scalars(
            select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
        )
    )
    perms = frozenset(
        db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id)
        )
    )
    return roles, perms


def _session_from_cookie(request: Request, db: Session) -> SessionRow:
    cookie = request.cookies.get(SESSION_COOKIE)
    key: bytes | None = request.app.state.cookie_key
    if key is None:
        raise ProblemError(
            503, "NOT_READY", "Not ready", "The master key is missing. Run 'tubeforge-admin init-keys'."
        )
    session_id = unsign_session(cookie, key) if cookie else None
    if session_id is None:
        raise unauthenticated()
    row = db.get(SessionRow, session_id)
    now = datetime.now(UTC)
    if (
        row is None
        or row.revoked_at is not None
        or row.expires_at <= now
        or row.last_seen_at + IDLE_TIMEOUT <= now
    ):
        raise unauthenticated("Your session has ended. Please sign in again.")
    if request.method not in SAFE_METHODS and not csrf_matches(
        request.headers.get(CSRF_HEADER), request.cookies.get(CSRF_COOKIE), row.csrf_token_hash
    ):
        raise ProblemError(
            403, "CSRF_FAILED", "Request blocked", "The security token is missing or wrong. Reload the page."
        )
    if now - row.last_seen_at >= TOUCH_EVERY:
        row.last_seen_at = now
        db.commit()
    return row


def _principal(request: Request, db: Session, *, require_mfa: bool) -> Principal:
    row = _session_from_cookie(request, db)
    user = db.get(User, row.user_id)
    if user is None or user.deleted_at is not None:
        raise unauthenticated()
    if require_mfa and user.totp_enabled and not row.mfa_passed:
        raise ProblemError(
            401, "MFA_REQUIRED", "Two-factor code needed", "Enter the code from your authenticator app."
        )
    roles, perms = load_permissions(db, user.id)
    principal = Principal(user=user, session=row, roles=roles, permissions=perms)
    request.state.principal = principal
    return principal


def public() -> None:
    """Marker: the route is intentionally reachable without a session (login only)."""


def pre_mfa(request: Request, db: Db) -> Principal:
    """Signed in, possibly before the two-factor step (MFA verify, logout, /auth/me)."""
    return _principal(request, db, require_mfa=False)


def authenticated(request: Request, db: Db) -> Principal:
    """Signed in and past two-factor (if enabled). No specific permission needed."""
    return _principal(request, db, require_mfa=True)


class Require:
    """``Depends(require("perm.code"))``: signed in, past MFA, and holding the permission."""

    def __init__(self, permission: str) -> None:
        self.permission = permission

    def __call__(self, request: Request, db: Db) -> Principal:
        principal = _principal(request, db, require_mfa=True)
        if not principal.has(self.permission):
            security_event(
                db,
                "PERMISSION_DENIED",
                "WARNING",
                user_id=principal.user.id,
                details={"permission": self.permission, "path": request.url.path},
            )
            db.commit()
            raise forbidden()
        return principal


def require(permission: str) -> Callable[..., Principal]:
    from tubeforge.auth.permissions import PERMISSIONS

    if permission not in PERMISSIONS:
        raise ValueError(f"unknown permission {permission!r}")
    return Require(permission)


def require_recent_reauth(principal: Principal) -> None:
    """Sensitive actions (OAUTH_SECURITY §2) need a password re-entry within the last 5 minutes."""
    reauth_at = principal.session.reauth_at
    if reauth_at is None or datetime.now(UTC) - reauth_at > REAUTH_WINDOW:
        raise ProblemError(
            403, "REAUTH_REQUIRED", "Confirm it's you", "This action needs your password again."
        )


def client_ip(request: Request) -> str | None:
    """The peer address if it is a real IP (sessions.ip / audit_log.ip are inet columns)."""
    host = request.client.host if request.client else None
    if not host:
        return None
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def request_id(request: Request) -> uuid.UUID | None:
    rid = getattr(request.state, "request_id", None)
    return rid if isinstance(rid, uuid.UUID) else None
