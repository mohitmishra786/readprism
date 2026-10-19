"""Lemon Squeezy adapter (#173).

Webhooks: `X-Signature` is the hex HMAC-SHA256 of the raw body with the
webhook signing secret. Events carry no id, so the body hash is the
idempotency key. Checkout links carry `checkout[custom][user_id]`, which
comes back as `meta.custom_data.user_id`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from urllib.parse import urlencode

from app.config import get_settings
from app.services.billing import ACTIVE, CANCELLED, ENDED, PAST_DUE, TRIALING, BillingUpdate

NAME = "lemonsqueezy"
_STATUS = {
    "active": ACTIVE,
    "on_trial": TRIALING,
    "past_due": PAST_DUE,
    "unpaid": PAST_DUE,
    "cancelled": CANCELLED,
    "expired": ENDED,
    "paused": ENDED,
}


def verify(raw: bytes, headers) -> bool:
    secret = get_settings().billing_webhook_secret
    signature = headers.get("x-signature") or ""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _dt(value) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse(raw: bytes) -> BillingUpdate:
    body = json.loads(raw)
    meta = body.get("meta") or {}
    data = body.get("data") or {}
    attrs = data.get("attributes") or {}
    event = str(meta.get("event_name") or "")
    custom = meta.get("custom_data") or {}
    try:
        user_id = uuid.UUID(str(custom.get("user_id"))) if custom.get("user_id") else None
    except ValueError:
        user_id = None
    is_subscription = data.get("type") == "subscriptions"
    status = _STATUS.get(str(attrs.get("status") or "")) if is_subscription else None
    return BillingUpdate(
        provider=NAME,
        key=f"{NAME}:{hashlib.sha256(raw).hexdigest()}",
        event_type=event or "unknown",
        occurred_at=_dt(attrs.get("updated_at")) or datetime.now(UTC),
        status=status,
        user_id=user_id,
        customer_id=str(attrs["customer_id"]) if attrs.get("customer_id") else None,
        subscription_id=str(data.get("id")) if is_subscription and data.get("id") else None,
        price_id=str(attrs["variant_id"]) if attrs.get("variant_id") else None,
        # Cancelled: access until ends_at. Otherwise: the renewal date.
        period_end=_dt(attrs.get("ends_at")) or _dt(attrs.get("renews_at")),
        portal_url=((attrs.get("urls") or {}).get("customer_portal")),
    )


async def checkout_url(user, interval: str) -> str | None:
    s = get_settings()
    base = s.billing_checkout_yearly if interval == "year" else s.billing_checkout_monthly
    if not base:
        return None
    params = {"checkout[email]": user.email, "checkout[custom][user_id]": str(user.id)}
    from app.services.billing import academic_discount_for

    if discount := academic_discount_for(user):
        params["checkout[discount_code]"] = discount  # academic discount (#250)
    query = urlencode(params)
    return f"{base}{'&' if '?' in base else '?'}{query}"


async def portal_url(user) -> str | None:
    return user.billing_portal_url
