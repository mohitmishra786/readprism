"""Encrypt secrets at rest with Fernet (#220, #255).

The key comes from SECRETS_ENCRYPTION_KEY, deliberately not SECRET_KEY:
rotating the session-signing key must not make stored secrets unreadable,
and a leak of one key must not expose the other. Each use passes its own
`purpose`, so the instance settings and per-user keys get different Fernet
keys from the same setting.
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings

__all__ = ["InvalidToken", "configured", "decrypt", "encrypt", "last4"]


class NotConfigured(RuntimeError):
    pass


def configured() -> bool:
    return bool(get_settings().secrets_encryption_key.strip())


def _fernet(purpose: str) -> Fernet:
    secret = get_settings().secrets_encryption_key.strip()
    if not secret:
        raise NotConfigured("SECRETS_ENCRYPTION_KEY is not set")
    raw = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"readprism-secretbox",
        info=purpose.encode(),
    ).derive(secret.encode())
    return Fernet(base64.urlsafe_b64encode(raw))


def encrypt(value: str, *, purpose: str) -> str:
    return _fernet(purpose).encrypt(value.encode()).decode()


def decrypt(token: str, *, purpose: str) -> str:
    return _fernet(purpose).decrypt(token.encode()).decode()


def last4(value: str) -> str:
    return value[-4:] if len(value) > 8 else ""
