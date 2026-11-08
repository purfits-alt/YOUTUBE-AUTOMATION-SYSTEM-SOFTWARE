"""OAUTH_SECURITY §10 "token encryption": ciphertext ≠ plaintext, tamper and AAD mismatch fail."""

from __future__ import annotations

import base64
import os

import pytest

from tubeforge.secrets import (
    ENV_KEY,
    DecryptionError,
    EnvStore,
    MasterKeyMissingError,
    MemoryStore,
    SecretBox,
    aad,
)


@pytest.fixture
def box() -> SecretBox:
    b = SecretBox(MemoryStore())
    assert b.ensure_master_key() is True
    assert b.ensure_master_key() is False
    return b


def test_round_trip_and_ciphertext_differs(box: SecretBox) -> None:
    secret = b"1//refresh-token-value"
    sealed = box.seal(secret, purpose="oauth", associated=aad("oauth_connections", "refresh_token_enc", "r1"))
    assert secret not in sealed.ciphertext
    assert sealed.key_id == "master-key-v1"
    out = box.open(
        sealed.ciphertext,
        key_id=sealed.key_id,
        purpose="oauth",
        associated=aad("oauth_connections", "refresh_token_enc", "r1"),
    )
    assert out == secret
    # Same plaintext twice → different ciphertexts (random nonce).
    again = box.seal(secret, purpose="oauth", associated=aad("oauth_connections", "refresh_token_enc", "r1"))
    assert again.ciphertext != sealed.ciphertext


def test_tampered_ciphertext_is_rejected(box: SecretBox) -> None:
    a = aad("users", "totp_secret_enc", "u1")
    sealed = bytearray(box.seal(b"JBSWY3DPEHPK3PXP", purpose="totp", associated=a).ciphertext)
    sealed[-1] ^= 0x01
    with pytest.raises(DecryptionError):
        box.open(bytes(sealed), key_id="master-key-v1", purpose="totp", associated=a)


def test_aad_and_purpose_bind_the_ciphertext(box: SecretBox) -> None:
    sealed = box.seal(
        b"k", purpose="provider", associated=aad("provider_credentials", "secret_enc", "gemini")
    )
    with pytest.raises(DecryptionError):  # copied to another row
        box.open(
            sealed.ciphertext,
            key_id="master-key-v1",
            purpose="provider",
            associated=aad("provider_credentials", "secret_enc", "groq"),
        )
    with pytest.raises(DecryptionError):  # other purpose → other data key
        box.open(
            sealed.ciphertext,
            key_id="master-key-v1",
            purpose="oauth",
            associated=aad("provider_credentials", "secret_enc", "gemini"),
        )


def test_missing_master_key() -> None:
    with pytest.raises(MasterKeyMissingError):
        SecretBox(MemoryStore()).seal(b"x", purpose="p", associated=b"a")


def test_env_store_for_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_KEY, base64.b64encode(os.urandom(32)).decode())
    box = SecretBox(EnvStore())
    sealed = box.seal(b"v", purpose="p", associated=b"a")
    assert box.open(sealed.ciphertext, key_id=sealed.key_id, purpose="p", associated=b"a") == b"v"
    assert box.keystore_ok()
