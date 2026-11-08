"""Argon2id password hashing and password policy (OAUTH_SECURITY §2)."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from zxcvbn import zxcvbn

# time_cost=3, memory_cost=64 MiB, parallelism=2 (OAUTH_SECURITY §2).
_HASHER = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)
MIN_LENGTH = 12
MIN_ZXCVBN_SCORE = 3
# Verified against an unknown e-mail so a missing account takes as long as a wrong password.
_DUMMY_HASH = _HASHER.hash("tubeforge-dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    try:
        return _HASHER.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    return _HASHER.check_needs_rehash(stored_hash)


def password_problems(password: str, *, user_inputs: list[str] | None = None) -> list[str]:
    """Reasons a new password is rejected (empty list = acceptable)."""
    problems = []
    if len(password) < MIN_LENGTH:
        problems.append(f"Use at least {MIN_LENGTH} characters.")
    result = zxcvbn(password[:100], user_inputs=user_inputs or [])
    if result["score"] < MIN_ZXCVBN_SCORE:
        hint = result["feedback"].get("warning") or "Add more words or characters."
        problems.append(f"Too easy to guess. {hint}".strip())
    return problems
