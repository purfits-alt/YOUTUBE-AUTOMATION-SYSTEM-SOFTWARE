"""Session and CSRF tokens (OAUTH_SECURITY §2).

``tf_session`` = ``<session uuid>.<HMAC-SHA256 signature>``. The session row id is random (UUIDv4);
the 256-bit HMAC key is derived from the master key, so a cookie cannot be forged from a guessed id.
``tf_csrf`` is a random token readable by the page (double-submit); the session stores its SHA-256.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid

SESSION_COOKIE = "tf_session"
CSRF_COOKIE = "tf_csrf"
CSRF_HEADER = "X-CSRF-Token"


def sign_session(session_id: uuid.UUID, key: bytes) -> str:
    sig = hmac.new(key, session_id.bytes, hashlib.sha256).digest()
    return f"{session_id}.{base64.urlsafe_b64encode(sig).decode().rstrip('=')}"


def unsign_session(cookie: str, key: bytes) -> uuid.UUID | None:
    try:
        raw_id, sig = cookie.split(".", 1)
        session_id = uuid.UUID(raw_id)
    except ValueError:
        return None
    expected = sign_session(session_id, key).split(".", 1)[1]
    return session_id if hmac.compare_digest(expected, sig) else None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_matches(header: str | None, cookie: str | None, stored_hash: str) -> bool:
    if not header or not cookie or not hmac.compare_digest(header, cookie):
        return False
    return hmac.compare_digest(sha256_hex(header), stored_hash)
