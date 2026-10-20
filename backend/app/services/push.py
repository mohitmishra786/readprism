"""Web Push digest alerts (#266): opt-in per device, VAPID-authenticated.

Implements the two standards directly on `cryptography` (already a
dependency through pyjwt) instead of pulling in pywebpush:

- RFC 8291 message encryption (aes128gcm content coding, RFC 8188): ECDH
  with the subscription's P-256 key, HKDF with its auth secret, one record.
- RFC 8292 VAPID: an ES256 JWT for the push service's origin, with the
  application server's public key in the Authorization header.

A push service answering 404 or 410 means the subscription is gone; it is
deleted. Endpoints must be public https URLs (SSRF guard).
"""

from __future__ import annotations

import base64
import json
import os
import time
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

RECORD_SIZE = 4096
TTL_SECONDS = 12 * 3600


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt(
    plaintext: bytes,
    *,
    p256dh: str,
    auth: str,
    salt: bytes | None = None,
    server_key: ec.EllipticCurvePrivateKey | None = None,
) -> bytes:
    """RFC 8291 aes128gcm body for one subscription. `salt` and `server_key`
    are injectable for tests; production uses fresh random ones."""
    ua_public_bytes = b64url_decode(p256dh)
    auth_secret = b64url_decode(auth)
    ua_public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public_bytes)
    server_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_public_bytes = server_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    salt = salt or os.urandom(16)

    shared = server_key.exchange(ec.ECDH(), ua_public)
    key_info = b"WebPush: info\x00" + ua_public_bytes + as_public_bytes
    ikm = _hkdf(auth_secret, shared, key_info, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)

    if len(plaintext) > RECORD_SIZE - 17 - 86:
        raise ValueError("push payload too large for one record")
    ciphertext = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)  # 0x02: last record
    header = salt + RECORD_SIZE.to_bytes(4, "big") + bytes([len(as_public_bytes)]) + as_public_bytes
    return header + ciphertext


def _private_key() -> ec.EllipticCurvePrivateKey:
    raw = b64url_decode(get_settings().vapid_private_key.strip())
    return ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())


def vapid_headers(endpoint: str) -> dict[str, str]:
    """RFC 8292 Authorization header for the push service behind `endpoint`."""
    import jwt

    s = get_settings()
    parts = urlparse(endpoint)
    claims = {
        "aud": f"{parts.scheme}://{parts.netloc}",
        "exp": int(time.time()) + TTL_SECONDS,
        "sub": s.vapid_subject,
    }
    pem = _private_key().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    token = jwt.encode(claims, pem, algorithm="ES256")
    return {"Authorization": f"vapid t={token}, k={s.vapid_public_key.strip()}"}


def push_enabled() -> bool:
    s = get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key and s.vapid_subject)


def endpoint_allowed(endpoint: str) -> bool:
    from app.utils.ssrf import UnsafeURLError, validate_public_url

    if urlparse(endpoint).scheme != "https":
        return False
    try:
        validate_public_url(endpoint)
    except UnsafeURLError:
        return False
    return True


async def send(subscription, payload: dict) -> str:
    """Send one notification. Returns 'sent', 'gone' (subscription expired)
    or 'failed'."""
    import httpx

    if not endpoint_allowed(subscription.endpoint):
        return "gone"
    body = encrypt(json.dumps(payload).encode(), p256dh=subscription.p256dh, auth=subscription.auth)
    headers = {
        **vapid_headers(subscription.endpoint),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(TTL_SECONDS),
        "Urgency": "normal",
    }
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            resp = await client.post(subscription.endpoint, content=body, headers=headers)
    except httpx.HTTPError as e:
        logger.warning(f"Push failed: {type(e).__name__}")
        return "failed"
    if resp.status_code in (404, 410):
        return "gone"
    if resp.status_code >= 400:
        logger.warning(f"Push rejected: HTTP {resp.status_code}")
        return "failed"
    return "sent"


async def notify_user(session, user_id, payload: dict) -> dict:
    """Send `payload` to every device the user opted in; prune dead ones."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.models.push import PushSubscription

    counts = {"sent": 0, "gone": 0, "failed": 0}
    if not push_enabled():
        return counts
    subs = (
        await session.execute(select(PushSubscription).where(PushSubscription.user_id == user_id))
    ).scalars()
    for sub in list(subs):
        outcome = await send(sub, payload)
        counts[outcome] += 1
        if outcome == "gone":
            await session.delete(sub)
        elif outcome == "sent":
            sub.last_success_at = datetime.now(UTC)
            sub.failure_count = 0
        else:
            sub.failure_count = (sub.failure_count or 0) + 1
    await session.flush()
    return counts


def digest_payload(total_items: int) -> dict:
    return {
        "title": "Your ReadPrism digest is ready",
        "body": f"{total_items} items ranked for you.",
        "url": "/digest",
        "tag": "readprism-digest",
    }
