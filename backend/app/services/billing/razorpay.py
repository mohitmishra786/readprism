"""Razorpay adapter (#342).

Webhooks: `X-Razorpay-Signature` is the hex HMAC-SHA256 of the raw body with the
webhook signing secret. Event payload contains subscription and payment entities.
Checkout creates a Razorpay subscription via their Subscriptions API with basic auth.
Razorpay is a payment gateway, not a merchant of record: tax (GST/VAT) responsibility
rests with the instance operator (D-25).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import get_settings
from app.services.billing import ACTIVE, CANCELLED, ENDED, PAST_DUE, BillingUpdate

NAME = "razorpay"
# No hosted customer portal: readers manage or cancel by contacting the operator.
HAS_PORTAL = False

# Razorpay subscription statuses normalized to internal states.
_EVENT_STATUS = {
    # "subscription.authenticated" is deliberately absent: the mandate is
    # authorised but nothing has been charged yet. The plan starts on
    # activated/charged.
    "subscription.activated": ACTIVE,
    "subscription.charged": ACTIVE,
    "subscription.pending": PAST_DUE,
    "subscription.halted": PAST_DUE,
    "subscription.cancelled": CANCELLED,
    "subscription.completed": ENDED,
    "subscription.expired": ENDED,
}

_ENTITY_STATUS = {
    "active": ACTIVE,
    "pending": PAST_DUE,
    "halted": PAST_DUE,
    "cancelled": CANCELLED,
    "completed": ENDED,
    "expired": ENDED,
}


def verify(raw: bytes, headers: Any) -> bool:
    """Verify HMAC-SHA256 signature from Razorpay webhook headers."""
    s = get_settings()
    secret = s.razorpay_webhook_secret or s.billing_webhook_secret
    signature = headers.get("x-razorpay-signature") or headers.get("X-Razorpay-Signature") or ""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        # Numeric unix timestamp in seconds
        if isinstance(value, int | float):
            return datetime.fromtimestamp(int(value), tz=UTC)
        if isinstance(value, str) and value.isdigit():
            return datetime.fromtimestamp(int(value), tz=UTC)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except Exception:
        return None


def parse(raw: bytes) -> BillingUpdate:
    """Parse a Razorpay webhook into a normalized BillingUpdate."""
    body = json.loads(raw)
    event = str(body.get("event") or "")
    payload = body.get("payload") or {}
    sub_data = (payload.get("subscription") or {}).get("entity") or {}
    payment_data = (payload.get("payment") or {}).get("entity") or {}

    is_subscription = event.startswith("subscription.") or bool(sub_data)
    status = _EVENT_STATUS.get(event) or _ENTITY_STATUS.get(str(sub_data.get("status") or ""))

    notes = sub_data.get("notes") or payment_data.get("notes") or {}
    user_id_raw = notes.get("user_id")
    user_id: uuid.UUID | None = None
    if user_id_raw:
        try:
            user_id = uuid.UUID(str(user_id_raw))
        except (ValueError, TypeError):
            user_id = None

    subscription_id = sub_data.get("id") if is_subscription else None
    customer_id = sub_data.get("customer_id") or payment_data.get("customer_id")
    price_id = sub_data.get("plan_id")

    period_end_val = (
        sub_data.get("current_end")
        or sub_data.get("charge_at")
        or sub_data.get("ended_at")
        or sub_data.get("end_at")
    )
    period_end = _dt(period_end_val)

    created_at_val = body.get("created_at")
    occurred_at = _dt(created_at_val) or datetime.now(UTC)

    event_id = body.get("event_id") or hashlib.sha256(raw).hexdigest()

    return BillingUpdate(
        provider=NAME,
        key=f"{NAME}:{event_id}",
        event_type=event or "unknown",
        occurred_at=occurred_at,
        status=status if is_subscription else None,
        user_id=user_id,
        customer_id=str(customer_id) if customer_id else None,
        subscription_id=str(subscription_id) if subscription_id else None,
        price_id=str(price_id) if price_id else None,
        period_end=period_end,
        portal_url=None,  # Razorpay does not offer a hosted customer portal
    )


async def checkout_url(user: Any, interval: str, plan: str = "reader") -> str | None:
    """Create a subscription via Razorpay API and return short_url."""
    from app.services.billing import checkout_target

    s = get_settings()
    key_id = s.razorpay_key_id
    key_secret = s.razorpay_key_secret
    if not key_id or not key_secret:
        return None

    plan_id = checkout_target(plan, interval)
    if not plan_id and plan == "pro":
        plan_id = s.razorpay_plan_id_pro

    if not plan_id:
        return None

    payload = {
        "plan_id": plan_id,
        # Billing cycles before Razorpay ends the subscription: 10 years either way.
        "total_count": 10 if interval == "year" else 120,
        "quantity": 1,
        "customer_notify": 1,
        # Only our id: Razorpay already has the customer's contact details.
        "notes": {"user_id": str(user.id)},
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.razorpay.com/v1/subscriptions",
            json=payload,
            auth=(key_id, key_secret),
        )
        resp.raise_for_status()
    data = resp.json()
    return data.get("short_url")


async def portal_url(user: Any) -> str | None:
    """Razorpay has no customer portal; returns None to let UI fall back to email support."""
    return None


async def cancel_subscription(subscription_id: str) -> None:
    """Cancel subscription immediately (account deletion, #221). Raises on failure."""
    s = get_settings()
    key_id = s.razorpay_key_id
    key_secret = s.razorpay_key_secret
    if not key_id or not key_secret:
        raise RuntimeError("Razorpay credentials are not configured")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://api.razorpay.com/v1/subscriptions/{subscription_id}/cancel",
            json={"cancel_at_cycle_end": 0},
            auth=(key_id, key_secret),
        )
        resp.raise_for_status()
