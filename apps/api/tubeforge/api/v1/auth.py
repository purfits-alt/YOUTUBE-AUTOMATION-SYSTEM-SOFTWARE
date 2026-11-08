"""Auth & session endpoints (BACKEND_SPECIFICATION §4.1, OAUTH_SECURITY §2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from tubeforge.api.deps import (
    ABSOLUTE_TIMEOUT,
    Db,
    Principal,
    authenticated,
    client_ip,
    pre_mfa,
    public,
    request_id,
    require_recent_reauth,
)
from tubeforge.api.errors import ProblemError, not_found, problem_doc
from tubeforge.audit import Actor, record, security_event
from tubeforge.auth import passwords, totp
from tubeforge.auth.cookies import CSRF_COOKIE, SESSION_COOKIE, new_csrf_token, sha256_hex, sign_session
from tubeforge.db.ids import uuid7
from tubeforge.db.models import SecurityEvent, User, UserRecoveryCode
from tubeforge.db.models import Session as SessionRow
from tubeforge.secrets import SecretBox, aad

router = APIRouter(prefix="/auth", tags=["auth"])

LOCKOUT_FAILURES = 5
LOCKOUT_WINDOW = timedelta(minutes=15)


# ------------------------------------------------------------------ schemas
class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    timezone: str
    mfa_enabled: bool


class LoginIn(BaseModel):
    # Explicit ASCII whitespace: "\s" means different things in Python and JSON-Schema regex.
    email: str = Field(pattern=r"^[^@ \t\r\n]+@[^@ \t\r\n]+\.[^@ \t\r\n]+$", max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class LoginOut(BaseModel):
    user: UserOut
    mfa_required: bool


class MeOut(BaseModel):
    user: UserOut
    roles: list[str]
    permissions: list[str]
    mfa_enabled: bool
    mfa_passed: bool
    reauth_valid_until: datetime | None


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class ReauthIn(BaseModel):
    password: str = Field(min_length=1, max_length=1024)
    code: str | None = Field(default=None, max_length=20)


class PasswordIn(BaseModel):
    current: str = Field(min_length=1, max_length=1024)
    new: str = Field(min_length=1, max_length=1024)


class MfaEnrollOut(BaseModel):
    otpauth_uri: str
    qr_svg: str


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str]


class SessionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    user_agent: str | None
    ip: str | None
    current: bool


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        timezone=user.timezone,
        mfa_enabled=user.totp_enabled,
    )


# ------------------------------------------------------------------ helpers
def _box(request: Request) -> SecretBox:
    box: SecretBox = request.app.state.secret_box
    return box


def _set_cookies(request: Request, response: Response, session_id: uuid.UUID, csrf: str) -> None:
    secure: bool = request.app.state.settings.env == "prod" and request.url.scheme == "https"
    max_age = int(ABSOLUTE_TIMEOUT.total_seconds())
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(session_id, request.app.state.cookie_key),
        max_age=max_age,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE, csrf, max_age=max_age, httponly=False, samesite="strict", secure=secure, path="/"
    )


def _new_session(request: Request, db: Db, user: User, *, mfa_passed: bool) -> tuple[SessionRow, str]:
    now = datetime.now(UTC)
    csrf = new_csrf_token()
    row = SessionRow(
        id=uuid.uuid4(),
        user_id=user.id,
        csrf_token_hash=sha256_hex(csrf),
        mfa_passed=mfa_passed,
        last_seen_at=now,
        expires_at=now + ABSOLUTE_TIMEOUT,
        user_agent=(request.headers.get("user-agent") or "")[:300] or None,
        ip=client_ip(request),
    )
    db.add(row)
    db.flush()
    return row, csrf


def _totp_secret(request: Request, user: User) -> str:
    if user.totp_secret_enc is None or user.totp_key_id is None:
        raise ProblemError(409, "MFA_NOT_ENROLLED", "Two-factor is not set up", "Start enrolment first.")
    return (
        _box(request)
        .open(
            user.totp_secret_enc,
            key_id=user.totp_key_id,
            purpose="totp",
            associated=aad("users", "totp_secret_enc", user.id),
        )
        .decode()
    )


def _check_second_factor(request: Request, db: Db, user: User, code: str) -> bool:
    """A TOTP code, or an unused recovery code (which is then consumed)."""
    if totp.verify_code(_totp_secret(request, user), code):
        return True
    normalised = totp.normalise_recovery_code(code)
    for rc in db.scalars(
        select(UserRecoveryCode).where(
            UserRecoveryCode.user_id == user.id, UserRecoveryCode.used_at.is_(None)
        )
    ):
        if passwords.verify_password(rc.code_hash, normalised):
            rc.used_at = datetime.now(UTC)
            return True
    return False


def _audit(request: Request, db: Db, actor: Actor, action: str, user: User, **details: object) -> None:
    record(
        db,
        actor=actor,
        action=action,
        entity_type="user",
        entity_id=str(user.id),
        details=dict(details),
        request_id=request_id(request),
        ip=client_ip(request),
    )


# ------------------------------------------------------------------ routes
@router.post(
    "/login",
    response_model=LoginOut,
    dependencies=[Depends(public)],
    responses={423: problem_doc("LOCKED after 5 failures in 15 min")},
)
def login(body: LoginIn, request: Request, response: Response, db: Db) -> LoginOut:
    if request.app.state.cookie_key is None:
        raise ProblemError(
            503, "NOT_READY", "Not ready", "The master key is missing. Run 'tubeforge-admin init-keys'."
        )
    now = datetime.now(UTC)
    user = db.scalar(select(User).where(User.email == body.email, User.deleted_at.is_(None)))
    if user is not None and user.locked_until is not None and user.locked_until > now:
        security_event(db, "LOGIN_LOCKED", "WARNING", user_id=user.id)
        db.commit()
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        raise ProblemError(
            423, "LOCKED", "Account locked", f"Too many wrong passwords. Try again in {minutes} min."
        )
    if user is None or not passwords.verify_password(user.password_hash, body.password):
        security_event(
            db, "LOGIN_FAILED", "WARNING", user_id=user.id if user else None, details={"email": body.email}
        )
        if user is not None:
            recent = db.scalar(
                select(func.count())
                .select_from(SecurityEvent)
                .where(
                    SecurityEvent.kind == "LOGIN_FAILED",
                    SecurityEvent.user_id == user.id,
                    SecurityEvent.occurred_at > now - LOCKOUT_WINDOW,
                )
            )
            user.failed_login_count += 1
            if (recent or 0) >= LOCKOUT_FAILURES:
                user.locked_until = now + LOCKOUT_WINDOW
                security_event(db, "LOCKOUT", "WARNING", user_id=user.id, details={"minutes": 15})
        db.commit()
        raise ProblemError(401, "BAD_CREDENTIALS", "Sign-in failed", "The e-mail or password is not correct.")
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(body.password)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    session, csrf = _new_session(request, db, user, mfa_passed=not user.totp_enabled)
    _audit(request, db, Actor("OWNER", str(user.id)), "auth.login", user, mfa_pending=user.totp_enabled)
    db.commit()
    _set_cookies(request, response, session.id, csrf)
    return LoginOut(user=user_out(user), mfa_required=user.totp_enabled)


@router.post("/mfa/verify", response_model=LoginOut)
def mfa_verify(
    body: CodeIn,
    request: Request,
    response: Response,
    db: Db,
    principal: Annotated[Principal, Depends(pre_mfa)],
) -> LoginOut:
    user = principal.user
    if not user.totp_enabled:
        raise ProblemError(409, "MFA_NOT_ENABLED", "Two-factor is off", "There is no code to check.")
    if not _check_second_factor(request, db, user, body.code):
        security_event(db, "MFA_FAILED", "WARNING", user_id=user.id)
        db.commit()
        raise ProblemError(401, "BAD_CODE", "Code not accepted", "Check the code in your authenticator app.")
    # Privilege change → rotate the session (OAUTH_SECURITY §2).
    principal.session.revoked_at = datetime.now(UTC)
    session, csrf = _new_session(request, db, user, mfa_passed=True)
    _audit(request, db, principal.actor, "auth.mfa_verify", user)
    db.commit()
    _set_cookies(request, response, session.id, csrf)
    return LoginOut(user=user_out(user), mfa_required=False)


@router.post("/logout", status_code=204)
def logout(
    request: Request, response: Response, db: Db, principal: Annotated[Principal, Depends(pre_mfa)]
) -> None:
    principal.session.revoked_at = datetime.now(UTC)
    _audit(request, db, principal.actor, "auth.logout", principal.user)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.get("/me", response_model=MeOut)
def me(principal: Annotated[Principal, Depends(pre_mfa)]) -> MeOut:
    from tubeforge.api.deps import REAUTH_WINDOW

    s = principal.session
    return MeOut(
        user=user_out(principal.user),
        roles=sorted(principal.roles),
        permissions=sorted(principal.permissions),
        mfa_enabled=principal.user.totp_enabled,
        mfa_passed=s.mfa_passed,
        reauth_valid_until=s.reauth_at + REAUTH_WINDOW if s.reauth_at else None,
    )


@router.post("/reauth", status_code=204)
def reauth(
    body: ReauthIn, request: Request, db: Db, principal: Annotated[Principal, Depends(authenticated)]
) -> None:
    user = principal.user
    ok = passwords.verify_password(user.password_hash, body.password)
    if ok and user.totp_enabled:
        ok = body.code is not None and _check_second_factor(request, db, user, body.code)
    if not ok:
        security_event(db, "REAUTH_FAILED", "WARNING", user_id=user.id)
        db.commit()
        raise ProblemError(
            401, "BAD_CREDENTIALS", "Not accepted", "That password (or code) was not accepted."
        )
    principal.session.reauth_at = datetime.now(UTC)
    _audit(request, db, principal.actor, "auth.reauth", user)
    db.commit()


@router.post("/password", status_code=204)
def change_password(
    body: PasswordIn, request: Request, db: Db, principal: Annotated[Principal, Depends(authenticated)]
) -> None:
    require_recent_reauth(principal)
    user = principal.user
    if not passwords.verify_password(user.password_hash, body.current):
        raise ProblemError(
            400,
            "VALIDATION_ERROR",
            "Invalid request",
            "The current password is not correct.",
            errors=[{"field": "current", "message": "Not correct."}],
        )
    problems = passwords.password_problems(body.new, user_inputs=[user.email, user.display_name])
    if problems:
        raise ProblemError(
            400,
            "VALIDATION_ERROR",
            "Invalid request",
            " ".join(problems),
            errors=[{"field": "new", "message": p} for p in problems],
        )
    user.password_hash = passwords.hash_password(body.new)
    now = datetime.now(UTC)
    db.execute(
        update(SessionRow)
        .where(
            SessionRow.user_id == user.id,
            SessionRow.id != principal.session.id,
            SessionRow.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    _audit(request, db, principal.actor, "auth.password_change", user, other_sessions_revoked=True)
    db.commit()


@router.post("/mfa/enroll", response_model=MfaEnrollOut)
def mfa_enroll(
    request: Request, db: Db, principal: Annotated[Principal, Depends(authenticated)]
) -> MfaEnrollOut:
    require_recent_reauth(principal)
    user = principal.user
    if user.totp_enabled:
        raise ProblemError(
            409, "MFA_ALREADY_ENABLED", "Two-factor is already on", "Disable it first to re-enrol."
        )
    secret = totp.new_secret()
    sealed = _box(request).seal(
        secret.encode(), purpose="totp", associated=aad("users", "totp_secret_enc", user.id)
    )
    user.totp_secret_enc, user.totp_key_id = sealed.ciphertext, sealed.key_id
    _audit(request, db, principal.actor, "auth.mfa_enroll", user)
    db.commit()
    uri = totp.provisioning_uri(secret, user.email)
    return MfaEnrollOut(otpauth_uri=uri, qr_svg=totp.qr_svg(uri))


@router.post("/mfa/confirm", response_model=RecoveryCodesOut)
def mfa_confirm(
    body: CodeIn, request: Request, db: Db, principal: Annotated[Principal, Depends(authenticated)]
) -> RecoveryCodesOut:
    user = principal.user
    if user.totp_enabled:
        raise ProblemError(409, "MFA_ALREADY_ENABLED", "Two-factor is already on", None)
    if not totp.verify_code(_totp_secret(request, user), body.code):
        raise ProblemError(400, "BAD_CODE", "Code not accepted", "Check the code in your authenticator app.")
    user.totp_enabled = True
    principal.session.mfa_passed = True
    db.execute(
        update(UserRecoveryCode).where(UserRecoveryCode.user_id == user.id).values(used_at=datetime.now(UTC))
    )
    codes = totp.new_recovery_codes()
    for code in codes:
        db.add(
            UserRecoveryCode(
                id=uuid7(),
                user_id=user.id,
                code_hash=passwords.hash_password(totp.normalise_recovery_code(code)),
            )
        )
    _audit(request, db, principal.actor, "auth.mfa_enable", user)
    db.commit()
    return RecoveryCodesOut(recovery_codes=codes)


@router.delete("/mfa", status_code=204)
def mfa_disable(request: Request, db: Db, principal: Annotated[Principal, Depends(authenticated)]) -> None:
    require_recent_reauth(principal)
    user = principal.user
    user.totp_enabled = False
    user.totp_secret_enc = None
    user.totp_key_id = None
    db.execute(
        update(UserRecoveryCode).where(UserRecoveryCode.user_id == user.id).values(used_at=datetime.now(UTC))
    )
    security_event(db, "MFA_DISABLED", "WARNING", user_id=user.id)
    _audit(request, db, principal.actor, "auth.mfa_disable", user)
    db.commit()


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(db: Db, principal: Annotated[Principal, Depends(authenticated)]) -> list[SessionOut]:
    now = datetime.now(UTC)
    rows = db.scalars(
        select(SessionRow)
        .where(
            SessionRow.user_id == principal.user.id,
            SessionRow.revoked_at.is_(None),
            SessionRow.expires_at > now,
        )
        .order_by(SessionRow.last_seen_at.desc())
    )
    return [
        SessionOut(
            id=r.id,
            created_at=r.created_at,
            last_seen_at=r.last_seen_at,
            expires_at=r.expires_at,
            user_agent=r.user_agent,
            ip=str(r.ip) if r.ip else None,
            current=r.id == principal.session.id,
        )
        for r in rows
    ]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(
    session_id: uuid.UUID, request: Request, db: Db, principal: Annotated[Principal, Depends(authenticated)]
) -> None:
    row = db.get(SessionRow, session_id)
    if row is None or row.user_id != principal.user.id or row.revoked_at is not None:
        raise not_found("Session not found.")
    row.revoked_at = datetime.now(UTC)
    record(
        db,
        actor=principal.actor,
        action="auth.session_revoke",
        entity_type="session",
        entity_id=str(row.id),
        request_id=request_id(request),
        ip=client_ip(request),
    )
    db.commit()


__all__ = ["router"]
