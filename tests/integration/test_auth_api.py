"""Auth & security tests (OAUTH_SECURITY §10, IMPLEMENTATION_ROADMAP Phase 3)."""

from __future__ import annotations

import pyotp
import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import BASE_URL, OWNER_EMAIL, OWNER_PASSWORD, VIEWER_EMAIL, Env, login

pytestmark = pytest.mark.integration


def test_login_me_logout(env: Env) -> None:
    with env.client() as c:
        assert c.get("/api/v1/auth/me").status_code == 401
        h = login(c)
        cookie = c.cookies["tf_session"]
        assert "." in cookie
        me = c.get("/api/v1/auth/me").json()
        assert me["user"]["email"] == OWNER_EMAIL
        assert me["roles"] == ["OWNER"]
        assert "emergency.clear" in me["permissions"] and me["mfa_enabled"] is False
        assert c.post("/api/v1/auth/logout", headers=h).status_code == 204
        assert c.get("/api/v1/auth/me").status_code == 401


def test_session_cookie_signature_is_checked(env: Env) -> None:
    with env.client() as c:
        login(c)
        real = c.cookies["tf_session"]
        session_id = real.split(".")[0]
        # Send ONLY the forged cookie: clear the jar first (httpx2's jar would otherwise keep the real
        # cookie next to the new one and send both).
        c.cookies.clear()
        c.cookies.set("tf_session", f"{session_id}.forged")
        r = c.get("/api/v1/auth/me")
        assert r.request.headers["cookie"] == f"tf_session={session_id}.forged"
        assert r.status_code == 401
        c.cookies.clear()
        c.cookies.set("tf_session", real)
        assert c.get("/api/v1/auth/me").status_code == 200  # the genuine cookie still works


def test_wrong_password_and_lockout(env: Env) -> None:
    with env.client() as c:
        for _ in range(5):
            r = c.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": "wrong password!!"})
            assert r.status_code == 401
            assert r.json()["code"] == "BAD_CREDENTIALS"
        # 6th attempt (even with the right password) → locked
        r = c.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
        assert r.status_code == 423
        assert r.json()["code"] == "LOCKED"
    kinds = [k for (k,) in env.sql("SELECT kind FROM security_events ORDER BY id")]
    assert kinds.count("LOGIN_FAILED") == 5 and "LOCKOUT" in kinds and "LOGIN_LOCKED" in kinds


def test_unknown_email_is_indistinguishable(env: Env) -> None:
    with env.client() as c:
        r = c.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever-123"})
        assert r.status_code == 401 and r.json()["code"] == "BAD_CREDENTIALS"


def test_csrf_required_on_writes(owner_client: tuple[TestClient, dict[str, str]]) -> None:
    c, h = owner_client
    r = c.post("/api/v1/auth/logout")
    assert r.status_code == 403 and r.json()["code"] == "CSRF_FAILED"
    r = c.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "wrong"})
    assert r.status_code == 403
    assert c.post("/api/v1/auth/logout", headers=h).status_code == 204


def test_foreign_origin_and_host_rejected(env: Env) -> None:
    with env.client() as c:
        r = c.post(
            "/api/v1/auth/login",
            json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
            headers={"Origin": "https://evil.example"},
        )
        assert r.status_code == 403 and r.json()["code"] == "ORIGIN_REJECTED"
        ok = c.post(
            "/api/v1/auth/login",
            json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
            headers={"Origin": BASE_URL},
        )
        assert ok.status_code == 200
    with TestClient(env.client().app, base_url="http://evil.example:8765") as other:
        assert other.get("/api/v1/auth/me").status_code == 400


def test_step_up_totp_enrolment_and_login_with_mfa(env: Env) -> None:
    with env.client() as c:
        h = login(c)
        r = c.post("/api/v1/auth/mfa/enroll", headers=h)
        assert r.status_code == 403 and r.json()["code"] == "REAUTH_REQUIRED"
        assert c.post("/api/v1/auth/reauth", json={"password": "nope"}, headers=h).status_code == 401
        assert c.post("/api/v1/auth/reauth", json={"password": OWNER_PASSWORD}, headers=h).status_code == 204
        enrol = c.post("/api/v1/auth/mfa/enroll", headers=h).json()
        assert enrol["otpauth_uri"].startswith("otpauth://totp/TubeForge") and "<svg" in enrol["qr_svg"]
        secret = pyotp.parse_uri(enrol["otpauth_uri"]).secret
        assert c.post("/api/v1/auth/mfa/confirm", json={"code": "000000"}, headers=h).status_code == 400
        codes = c.post("/api/v1/auth/mfa/confirm", json={"code": pyotp.TOTP(secret).now()}, headers=h).json()
        assert len(codes["recovery_codes"]) == 10
        stored = env.sql("SELECT totp_secret_enc FROM users WHERE email = :e", e=OWNER_EMAIL)[0][0]
        assert secret.encode() not in bytes(stored)  # encrypted at rest

    with env.client() as c:
        r = c.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
        assert r.json()["mfa_required"] is True
        h = {"X-CSRF-Token": c.cookies["tf_csrf"]}
        assert c.get("/api/v1/auth/me").status_code == 200  # allowed before MFA
        blocked = c.get("/api/v1/audit-log")
        assert blocked.status_code == 401 and blocked.json()["code"] == "MFA_REQUIRED"
        assert c.post("/api/v1/auth/mfa/verify", json={"code": "123456"}, headers=h).status_code == 401
        recovery = codes["recovery_codes"][0]
        assert c.post("/api/v1/auth/mfa/verify", json={"code": recovery}, headers=h).status_code == 200
        assert c.get("/api/v1/audit-log").status_code == 200

    with env.client() as c:  # a recovery code works only once
        c.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
        h = {"X-CSRF-Token": c.cookies["tf_csrf"]}
        assert c.post("/api/v1/auth/mfa/verify", json={"code": recovery}, headers=h).status_code == 401
        assert (
            c.post("/api/v1/auth/mfa/verify", json={"code": pyotp.TOTP(secret).now()}, headers=h).status_code
            == 200
        )


def test_password_change_policy_and_other_sessions_revoked(env: Env) -> None:
    with env.client() as other:
        login(other)
        with env.client() as c:
            h = login(c)
            c.post("/api/v1/auth/reauth", json={"password": OWNER_PASSWORD}, headers=h)
            weak = c.post(
                "/api/v1/auth/password", json={"current": OWNER_PASSWORD, "new": "password123"}, headers=h
            )
            assert weak.status_code == 400 and weak.json()["errors"][0]["field"] == "new"
            ok = c.post(
                "/api/v1/auth/password",
                json={"current": OWNER_PASSWORD, "new": "plum violet harbour 77 lantern"},
                headers=h,
            )
            assert ok.status_code == 204
            assert c.get("/api/v1/auth/me").status_code == 200
        assert other.get("/api/v1/auth/me").status_code == 401


def test_viewer_is_forbidden_and_it_is_logged(env: Env, add_user) -> None:  # type: ignore[no-untyped-def]
    add_user(VIEWER_EMAIL, "VIEWER")
    with env.client() as c:
        login(c, VIEWER_EMAIL)
        r = c.get("/api/v1/audit-log")
        assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN"
    assert ("PERMISSION_DENIED",) in env.sql("SELECT kind FROM security_events")


def test_every_write_creates_exactly_one_audit_row_and_chain_verifies(env: Env) -> None:
    with env.client() as c:
        h = login(c)  # write 1
        c.post("/api/v1/auth/reauth", json={"password": OWNER_PASSWORD}, headers=h)  # write 2
        c.post("/api/v1/auth/logout", headers=h)  # write 3
        h = login(c)  # write 4
        actions = [a for (a,) in env.sql("SELECT action FROM audit_log ORDER BY id")]
        assert actions == ["auth.login", "auth.reauth", "auth.logout", "auth.login"]
        page = c.get("/api/v1/audit-log", params={"limit": 2}).json()
        assert len(page["items"]) == 2 and page["next_cursor"]
        rest = c.get("/api/v1/audit-log", params={"limit": 2, "cursor": page["next_cursor"]}).json()
        assert [i["action"] for i in rest["items"]] == ["auth.reauth", "auth.login"]
        assert c.get("/api/v1/audit-log/verify-chain").json() == {
            "ok": True,
            "checked": 4,
            "first_broken_id": None,
        }

        # Tampering outside the app (the owner disables the append-only trigger) is detected.
        env.sql("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only")
        env.sql("UPDATE audit_log SET action = 'auth.nothing' WHERE id = (SELECT min(id) + 1 FROM audit_log)")
        env.sql("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only")
        broken = c.get("/api/v1/audit-log/verify-chain").json()
        assert broken["ok"] is False and broken["first_broken_id"] is not None


def test_problem_json_shape(env: Env) -> None:
    with env.client() as c:
        r = c.post("/api/v1/auth/login", json={"email": "not-an-email", "password": ""})
        body = r.json()
        assert r.status_code == 400 and r.headers["content-type"].startswith("application/problem+json")
        assert body["code"] == "VALIDATION_ERROR" and body["request_id"] == r.headers["X-Request-ID"]
        assert {e["field"] for e in body["errors"]} == {"email", "password"}


def test_nul_bytes_are_a_400_not_a_500(owner_client) -> None:  # type: ignore[no-untyped-def]
    """Regression (contract test): a NUL byte reached PostgreSQL and became a 500."""
    import uuid as _uuid

    client, headers = owner_client
    r = client.post("/api/v1/auth/login", json={"email": "own\x00er@example.com", "password": "x"})
    assert r.status_code == 400
    # Safety net for any other text field: the database's refusal becomes a VALIDATION_ERROR.
    r = client.post(
        "/api/v1/channels",
        json={"name": "bad\x00name", "content_language": "en"},
        headers={**headers, "Idempotency-Key": str(_uuid.uuid4())},
    )
    assert r.status_code == 400 and r.json()["code"] == "VALIDATION_ERROR"
