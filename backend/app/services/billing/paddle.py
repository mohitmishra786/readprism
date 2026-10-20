"""Paddle Billing adapter (#173).

Webhooks: `Paddle-Signature: ts=<unix>;h1=<hex>` where h1 is HMAC-SHA256 of
"<ts>:<raw body>" with the notification secret; a signature older than five
minutes is refused. `event_id` is the idempotency key. Checkout creates a
transaction with `custom_data.user_id` and redirects to its checkout URL.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime

import httpx

from app.config import get_settings
from app.services.billing import ACTIVE, CANCELLED, ENDED, PAST_DUE, TRIALING, BillingUpdate

NAME = "paddle"
MAX_SKEW_SECONDS = 300
_STATUS = {
    "active": ACTIVE,
    "trialing": TRIALING,
    "past_due": PAST_DUE,
    "paused": ENDED,
    "canceled": ENDED,  # Paddle only sends this once the subscription has ended
}


def _api() -> str:
    return (
        "https://sandbox-api.paddle.com"
        if get_settings().billing_sandbox
        else "https://api.paddle.com"
    )


def verify(raw: bytes, headers, *, now: float | None = None) -> bool:
    secret = get_settings().billing_webhook_secret
    header = headers.get("paddle-signature") or ""
    parts = dict(p.split("=", 1) for p in header.split(";") if "=" in p)
    ts, h1 = parts.get("ts"), parts.get("h1")
    if not secret or not ts or not h1:
        return False
    try:
        if abs((now or time.time()) - int(ts)) > MAX_SKEW_SECONDS:
            return False
    except ValueError:
        return False
    expected = hmac.new(secret.encode(), f"{ts}:".encode() + raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, h1)


def _dt(value) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse(raw: bytes) -> BillingUpdate:
    body = json.loads(raw)
    event = str(body.get("event_type") or "")
    data = body.get("data") or {}
    is_subscription = event.startswith("subscription.")
    status = _STATUS.get(str(data.get("status") or "")) if is_subscription else None
    scheduled = data.get("scheduled_change") or {}
    if status == ACTIVE and scheduled.get("action") == "cancel":
        status = CANCELLED
    custom = data.get("custom_data") or {}
    try:
        user_id = uuid.UUID(str(custom.get("user_id"))) if custom.get("user_id") else None
    except ValueError:
        user_id = None
    items = data.get("items") or []
    price_id = ((items[0].get("price") or {}).get("id")) if items else None
    period = data.get("current_billing_period") or {}
    end = _dt(scheduled.get("effective_at")) if status == CANCELLED else _dt(period.get("ends_at"))
    return BillingUpdate(
        provider=NAME,
        key=f"{NAME}:{body.get('event_id') or hashlib.sha256(raw).hexdigest()}",
        event_type=event or "unknown",
        occurred_at=_dt(body.get("occurred_at")) or datetime.now(UTC),
        status=status,
        user_id=user_id,
        customer_id=data.get("customer_id"),
        subscription_id=data.get("id") if is_subscription else None,
        price_id=price_id,
        period_end=end,
    )


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_settings().billing_api_key}"}


async def checkout_url(user, interval: str, plan: str = "reader") -> str | None:
    from app.services.billing import checkout_target

    s = get_settings()
    price = checkout_target(plan, interval)
    if not price or not s.billing_api_key:
        return None
    payload: dict = {
        "items": [{"price_id": price, "quantity": 1}],
        "custom_data": {"user_id": str(user.id)},
    }
    from app.services.billing import academic_discount_for

    if discount := academic_discount_for(user):
        payload["discount_id"] = discount  # academic discount (#250)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{_api()}/transactions", json=payload, headers=_headers())
        resp.raise_for_status()
    return ((resp.json().get("data") or {}).get("checkout") or {}).get("url")


async def portal_url(user) -> str | None:
    if not user.billing_customer_id or not get_settings().billing_api_key:
        return None
    body = (
        {"subscription_ids": [user.billing_subscription_id]} if user.billing_subscription_id else {}
    )
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{_api()}/customers/{user.billing_customer_id}/portal-sessions",
            json=body,
            headers=_headers(),
        )
        resp.raise_for_status()
    urls = (resp.json().get("data") or {}).get("urls") or {}
    return (urls.get("general") or {}).get("overview")
