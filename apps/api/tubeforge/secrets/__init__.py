"""Secrets: AES-256-GCM envelope encryption (OAUTH_SECURITY §5, ADR-0012).

- Master key (256-bit) lives in Windows Credential Manager via ``keyring``
  (service ``TubeForge``, user ``master-key-v1``). Linux/CI: ``TUBEFORGE_MASTER_KEY`` (base64) —
  test keys only; refused when ``TUBEFORGE_ENV=prod`` on Windows.
- Data keys are derived per purpose with HKDF-SHA256 (``info = purpose + key_id``).
- Ciphertext layout: 12-byte nonce || ciphertext || 16-byte tag. AAD = ``table:column:row_id`` so a
  ciphertext cannot be copied to another row or column.
"""

from __future__ import annotations

import base64
import os
import sys
from dataclasses import dataclass
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

KEYRING_SERVICE = "TubeForge"
CURRENT_KEY_ID = "master-key-v1"
ENV_KEY = "TUBEFORGE_MASTER_KEY"
NONCE_BYTES = 12


class SecretsError(Exception):
    """Base error. Messages never include secret material."""


class MasterKeyMissingError(SecretsError):
    pass


class DecryptionError(SecretsError):
    pass


class KeyStore(Protocol):
    def get(self, key_id: str) -> bytes | None: ...
    def put(self, key_id: str, key: bytes) -> None: ...


class KeyringStore:
    """Windows Credential Manager (or the OS keyring elsewhere)."""

    def get(self, key_id: str) -> bytes | None:
        import keyring

        value = keyring.get_password(KEYRING_SERVICE, key_id)
        return base64.b64decode(value) if value else None

    def put(self, key_id: str, key: bytes) -> None:
        import keyring

        keyring.set_password(KEYRING_SERVICE, key_id, base64.b64encode(key).decode("ascii"))


class EnvStore:
    """Test/CI only: one key from TUBEFORGE_MASTER_KEY."""

    def get(self, key_id: str) -> bytes | None:
        value = os.environ.get(ENV_KEY)
        return base64.b64decode(value) if value and key_id == CURRENT_KEY_ID else None

    def put(self, key_id: str, key: bytes) -> None:
        raise SecretsError("the environment key store is read-only; use the OS keyring")


class MemoryStore:
    """Unit tests."""

    def __init__(self) -> None:
        self._keys: dict[str, bytes] = {}

    def get(self, key_id: str) -> bytes | None:
        return self._keys.get(key_id)

    def put(self, key_id: str, key: bytes) -> None:
        self._keys[key_id] = key


def default_store(env: str) -> KeyStore:
    if os.environ.get(ENV_KEY):
        if env == "prod" and sys.platform == "win32":
            raise SecretsError("TUBEFORGE_MASTER_KEY is for tests only; production uses Credential Manager")
        return EnvStore()
    return KeyringStore()


def aad(table: str, column: str, row_id: object) -> bytes:
    return f"{table}:{column}:{row_id}".encode()


@dataclass(frozen=True)
class Sealed:
    ciphertext: bytes
    key_id: str


class SecretBox:
    def __init__(self, store: KeyStore, key_id: str = CURRENT_KEY_ID) -> None:
        self._store = store
        self.key_id = key_id

    def ensure_master_key(self) -> bool:
        """Create the master key if it does not exist yet. Returns True when one was created."""
        if self._store.get(self.key_id) is not None:
            return False
        self._store.put(self.key_id, AESGCM.generate_key(bit_length=256))
        return True

    def _data_key(self, purpose: str, key_id: str) -> bytes:
        master = self._store.get(key_id)
        if master is None:
            raise MasterKeyMissingError(f"master key {key_id!r} not found (run 'tubeforge-admin init-keys')")
        if len(master) != 32:
            raise SecretsError("master key has the wrong length")
        hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=f"{purpose}:{key_id}".encode())
        return hkdf.derive(master)

    def seal(self, plaintext: bytes, *, purpose: str, associated: bytes) -> Sealed:
        nonce = os.urandom(NONCE_BYTES)
        ct = AESGCM(self._data_key(purpose, self.key_id)).encrypt(nonce, plaintext, associated)
        return Sealed(ciphertext=nonce + ct, key_id=self.key_id)

    def open(self, sealed: bytes, *, key_id: str, purpose: str, associated: bytes) -> bytes:
        if len(sealed) < NONCE_BYTES + 16:
            raise DecryptionError("ciphertext too short")
        nonce, ct = sealed[:NONCE_BYTES], sealed[NONCE_BYTES:]
        try:
            return AESGCM(self._data_key(purpose, key_id)).decrypt(nonce, ct, associated)
        except InvalidTag as exc:
            raise DecryptionError("ciphertext was modified, or belongs to another row/column/key") from exc

    def keystore_ok(self) -> bool:
        try:
            return self._store.get(self.key_id) is not None
        except Exception:
            return False
