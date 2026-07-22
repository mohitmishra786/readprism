"""Signed one-click unsubscribe tokens for digest emails (audit 08-5).

A digest email must carry a working unsubscribe control (CAN-SPAM / RFC 8058
List-Unsubscribe-Post). We sign the user id with the app secret so the
unsubscribe endpoint needs no login and the link can't be forged to unsubscribe
someone else.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid

from app.config import get_settings

settings = get_settings()


def make_unsubscribe_token(user_id: uuid.UUID | str) -> str:
    return hmac.new(
        key=settings.secret_key.encode(),
        msg=f"unsubscribe:{user_id}".encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()


def verify_unsubscribe_token(user_id: uuid.UUID | str, token: str) -> bool:
    if not token:
        return False
    return hmac.compare_digest(make_unsubscribe_token(user_id), token)


def unsubscribe_url(user_id: uuid.UUID | str) -> str:
    token = make_unsubscribe_token(user_id)
    return f"{settings.public_api_url.rstrip('/')}/api/v1/digest/unsubscribe?uid={user_id}&token={token}"
