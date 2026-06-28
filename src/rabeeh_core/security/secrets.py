"""Symmetric encryption for secrets at rest.

Rabeeh sometimes needs to persist user-supplied credentials (e.g. a CRM API
key the Business agent reuses across runs). We never store these in plain
text; instead we wrap them with a Fernet token derived from the master
``RABEEH_SECRET_KEY``.

Why Fernet (AES-128-CBC + HMAC-SHA256)?
- Authenticated encryption: tampering is detected.
- Stateless: no DB row needed for an IV, the token is self-describing.
- Battle-tested in the ``cryptography`` package.

The master key is held by the OS/env, never in code or logs.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken

from ..config.settings import get_settings


class _SettingsLike(Protocol):
    secret_key: object  # SecretStr-compatible


def _derive_key(passphrase: str) -> bytes:
    """Derive a 32-byte url-safe key from an arbitrary passphrase.

    Fernet requires a 32-byte url-safe base64 key. We SHA-256 the passphrase
    (deterministic, sufficient for *wrapping* secrets whose plaintext lives
    only briefly in memory) and base64-encode the digest.

    Note: this is NOT a KDF suitable for user passwords; it is meant for an
    already-protected master key. For user-facing secrets use Argon2 (Phase 6).
    """
    digest = hashlib.sha256(passphrase.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


class SecretVault:
    """Encrypts/decrypts arbitrary strings using the master key.

    Stateless and thread-safe (Fernet is immutable); safe to share a single
    instance across the process.
    """

    def __init__(self, passphrase: str | None = None) -> None:
        """Initialise the vault.

        Args:
            passphrase: Master passphrase. If omitted, read from settings.
        """
        if passphrase is None:
            passphrase = get_settings().secret_key.get_secret_value()
        self._fernet = Fernet(_derive_key(passphrase))

    def encrypt(self, plaintext: str) -> str:
        """Encrypt ``plaintext`` -> Fernet token string (safe for DB storage)."""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        """Decrypt a Fernet token previously produced by :meth:`encrypt`.

        Raises:
            InvalidToken: if the token was tampered with or produced by
                another key.
        """
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:  # pragma: no cover - defensive branch
            raise InvalidToken("Failed to decrypt secret: wrong key or tampered data.") from exc
