"""Token encryption at rest using Fernet (symmetric AES-128-CBC + HMAC).

OAuth tokens are encrypted before being written to SQLite and decrypted
only in memory, only when a provider call needs them.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from .config import settings

_fernet = Fernet(settings.ENCRYPTION_KEY.encode("utf-8"))


def encrypt(plaintext: str | None) -> str:
    """Encrypt a string; empty/None become empty string."""
    if not plaintext:
        return ""
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str | None) -> str:
    """Decrypt a string; empty/None become empty string.

    Returns "" (never raises) if the token is invalid or corrupted so a
    single bad token cannot crash a sync cycle.
    """
    if not ciphertext:
        return ""
    try:
        return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
