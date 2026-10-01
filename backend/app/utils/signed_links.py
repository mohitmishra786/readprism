"""Signed, expiring one-click action links for digest emails (UX-04).

Email feedback links must work without a login and must not be forgeable:
anyone who can guess a URL must not be able to rate or save on another
user's behalf. Each link carries the user id, the item id, the action, and
an expiry, all bound by an HMAC over the app secret (same key family as the
unsubscribe token). Links expire so a forwarded email stops working after
the TTL.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid

from app.config import get_settings

ACTIONS = ("open", "up", "down", "save")
DEFAULT_TTL_SECONDS = 30 * 24 * 3600  # 30 days


def _signature(user_id: uuid.UUID | str, item_id: uuid.UUID | str, action: str, exp: int) -> str:
    message = f"email-action:{user_id}:{item_id}:{action}:{exp}".encode()
    return hmac.new(
        key=get_settings().secret_key.encode(),
        msg=message,
        digestmod=hashlib.sha256,
    ).hexdigest()


def action_url(
    user_id: uuid.UUID | str,
    item_id: uuid.UUID | str,
    action: str,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> str:
    if action not in ACTIONS:
        raise ValueError(f"unknown action: {action}")
    exp = int((now if now is not None else time.time()) + ttl_seconds)
    sig = _signature(user_id, item_id, action, exp)
    base = get_settings().public_api_url.rstrip("/")
    return f"{base}/api/v1/digest/e/{action}/{item_id}" f"?uid={user_id}&exp={exp}&sig={sig}"


def verify_action(
    user_id: uuid.UUID | str,
    item_id: uuid.UUID | str,
    action: str,
    exp: int,
    sig: str,
    *,
    now: float | None = None,
) -> bool:
    if action not in ACTIONS:
        return False
    if not sig:
        return False
    if int(exp) < int(now if now is not None else time.time()):
        return False
    return hmac.compare_digest(_signature(user_id, item_id, action, int(exp)), sig)
