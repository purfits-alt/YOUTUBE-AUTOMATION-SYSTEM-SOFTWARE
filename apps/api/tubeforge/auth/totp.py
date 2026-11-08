"""TOTP (RFC 6238: SHA-1, 6 digits, 30 s, ±1 step) and recovery codes (OAUTH_SECURITY §2)."""

from __future__ import annotations

import secrets

import pyotp
import segno

ISSUER = "TubeForge"
RECOVERY_CODE_COUNT = 10


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, account: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=ISSUER)


def qr_svg(uri: str) -> str:
    return segno.make(uri, error="m").svg_inline(scale=4, dark="#111827", light="#ffffff")


def verify_code(secret: str, code: str) -> bool:
    code = code.strip().replace(" ", "")
    return code.isdigit() and len(code) == 6 and pyotp.TOTP(secret).verify(code, valid_window=1)


def new_recovery_codes() -> list[str]:
    """Ten codes like 'k7m2-q9xd-4tnw' (shown once; stored Argon2-hashed)."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return [
        "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3))
        for _ in range(RECOVERY_CODE_COUNT)
    ]


def normalise_recovery_code(code: str) -> str:
    return code.strip().lower().replace(" ", "")
