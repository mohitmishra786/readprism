"""Razorpay billing adapter tests (#342)."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.config import get_settings
from app.models.billing import BillingEvent
from app.models.user import User
from app.services import billing
from app.services.billing import razorpay

SECRET = "rzp_webhook_secret_test"
KEY_ID = "rzp_test_key_123"
KEY_SECRET = "rzp_test_secret_456"
PLAN_PRO_ID = "plan_pro_razorpay_789"


@pytest.fixture
def hosted_razorpay(monkeypatch):
    s = get_settings()
    for key, value in {
        "deployment_mode": "hosted",
        "registration_mode": "open",
        "email_verification": "off",
        "billing_provider": "razorpay",
        "razorpay_webhook_secret": SECRET,
        "razorpay_key_id": KEY_ID,
        "razorpay_key_secret": KEY_SECRET,
        "razorpay_plan_id_pro": PLAN_PRO_ID,
        "billing_pro_price_ids": PLAN_PRO_ID,
        "billing_checkout_pro_monthly": PLAN_PRO_ID,
        "billing_trial_days": 30,
    }.items():
        monkeypatch.setattr(s, key, value)
    return s


async def _user(db_session, **kw) -> User:
    user = User(email=f"rzp_{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", **kw)
    db_session.add(user)
    await db_session.commit()
    return user


def _rzp_event(
    event: str,
    user_id: uuid.UUID,
    *,
    sub_id: str = "sub_test_123",
    plan_id: str = PLAN_PRO_ID,
    status: str = "active",
    current_end: int | None = None,
    created_at: int | None = None,
) -> bytes:
    created = created_at or int(datetime.now(UTC).timestamp())
    end = current_end or (created + 30 * 86400)
    body = {
        "entity": "event",
        "account_id": "acc_test",
        "event": event,
        "contains": ["subscription"],
        "payload": {
            "subscription": {
                "entity": {
                    "id": sub_id,
                    "plan_id": plan_id,
                    "customer_id": "cust_test_999",
                    "status": status,
                    "current_start": created,
                    "current_end": end,
                    "ended_at": end if status in ("cancelled", "completed", "expired") else None,
                    "charge_at": end,
                    "notes": {
                        "user_id": str(user_id),
                    },
                }
            }
        },
        "created_at": created,
    }
    return json.dumps(body).encode()


async def _post_rzp(client: AsyncClient, raw: bytes, *, secret: str = SECRET):
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return await client.post(
        "/api/v1/billing/webhook/razorpay",
        content=raw,
        headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
    )


@pytest.mark.asyncio
async def test_razorpay_signature_verification(client: AsyncClient, hosted_razorpay):
    raw = b'{"event":"dummy"}'
    # Valid signature
    sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    assert razorpay.verify(raw, {"x-razorpay-signature": sig})

    # Wrong signature returns 401
    res_bad = await client.post(
        "/api/v1/billing/webhook/razorpay",
        content=raw,
        headers={"X-Razorpay-Signature": "invalidsig", "Content-Type": "application/json"},
    )
    assert res_bad.status_code == 401

    # Missing signature returns 401
    res_missing = await client.post(
        "/api/v1/billing/webhook/razorpay",
        content=raw,
        headers={"Content-Type": "application/json"},
    )
    assert res_missing.status_code == 401


@pytest.mark.asyncio
async def test_razorpay_subscription_activated_upgrades_user(
    client: AsyncClient, db_session, hosted_razorpay
):
    user = await _user(db_session)
    t0 = int(datetime.now(UTC).timestamp())
    t_end = t0 + 30 * 86400

    raw = _rzp_event("subscription.activated", user.id, current_end=t_end, created_at=t0)
    res = await _post_rzp(client, raw)
    assert res.status_code == 200
    assert res.json()["status"] == "applied"

    await db_session.refresh(user)
    assert user.tier == "pro"
    assert billing.effective_plan(user) == "pro"
    assert user.billing_provider == "razorpay"
    assert user.billing_subscription_id == "sub_test_123"
    assert user.billing_customer_id == "cust_test_999"
    assert user.billing_status == "active"
    assert user.billing_portal_url is None
    assert user.plan_expires_at is not None

    # Exact replay is recorded once and skipped
    res_dup = await _post_rzp(client, raw)
    assert res_dup.status_code == 200
    assert res_dup.json()["status"] == "duplicate"


@pytest.mark.asyncio
async def test_razorpay_subscription_cancelled_keeps_access_until_period_end(
    client: AsyncClient, db_session, hosted_razorpay
):
    user = await _user(db_session)
    t0 = int(datetime.now(UTC).timestamp())
    t_end = t0 + 15 * 86400

    # First activate
    act_raw = _rzp_event("subscription.activated", user.id, current_end=t_end, created_at=t0)
    await _post_rzp(client, act_raw)

    # Then cancel with newer timestamp
    t1 = t0 + 100
    cancel_raw = _rzp_event(
        "subscription.cancelled",
        user.id,
        status="cancelled",
        current_end=t_end,
        created_at=t1,
    )
    res_cancel = await _post_rzp(client, cancel_raw)
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "applied"

    await db_session.refresh(user)
    assert user.billing_status == "cancelled"
    # Still Pro before period end
    assert billing.effective_plan(user, now=datetime.fromtimestamp(t0 + 500, tz=UTC)) == "pro"


@pytest.mark.asyncio
async def test_razorpay_subscription_completed_downgrades_to_free(
    client: AsyncClient, db_session, hosted_razorpay
):
    user = await _user(db_session)
    t0 = int(datetime.now(UTC).timestamp())

    # Activate
    act_raw = _rzp_event("subscription.activated", user.id, created_at=t0)
    await _post_rzp(client, act_raw)

    # Expire / complete
    t1 = t0 + 200
    completed_raw = _rzp_event(
        "subscription.completed",
        user.id,
        status="completed",
        created_at=t1,
    )
    res_comp = await _post_rzp(client, completed_raw)
    assert res_comp.status_code == 200
    assert res_comp.json()["status"] == "applied"

    await db_session.refresh(user)
    assert user.tier == "free"
    assert billing.effective_plan(user) == "paused"


@pytest.mark.asyncio
async def test_razorpay_stale_event_rejected(client: AsyncClient, db_session, hosted_razorpay):
    user = await _user(db_session)
    t_now = int(datetime.now(UTC).timestamp())

    # Newer event applied first
    new_raw = _rzp_event("subscription.activated", user.id, created_at=t_now + 500)
    await _post_rzp(client, new_raw)

    # Older event arrives later
    old_raw = _rzp_event("subscription.charged", user.id, created_at=t_now)
    res_old = await _post_rzp(client, old_raw)
    assert res_old.status_code == 200
    assert res_old.json()["status"] == "stale"


@pytest.mark.asyncio
async def test_razorpay_checkout_flow(client: AsyncClient, db_session, hosted_razorpay):
    user = await _user(db_session)

    # Mock Razorpay Subscriptions API response
    fake_response = httpx.Response(
        status_code=200,
        json={
            "id": "sub_rzp_mock_1",
            "plan_id": PLAN_PRO_ID,
            "status": "created",
            "short_url": "https://rzp.io/i/test_mock_sub",
        },
        request=httpx.Request("POST", "https://api.razorpay.com/v1/subscriptions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = fake_response

        url = await razorpay.checkout_url(user, interval="month", plan="pro")
        assert url == "https://rzp.io/i/test_mock_sub"

        # Check call arguments
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.razorpay.com/v1/subscriptions"
        assert kwargs["auth"] == (KEY_ID, KEY_SECRET)
        payload = kwargs["json"]
        assert payload["plan_id"] == PLAN_PRO_ID
        assert payload["notes"]["user_id"] == str(user.id)


@pytest.mark.asyncio
async def test_razorpay_portal_and_cancellation(hosted_razorpay):
    # Portal URL returns None for Razorpay
    fake_user = User(email="test@example.com")
    assert await razorpay.portal_url(fake_user) is None

    # Cancel subscription
    fake_cancel_response = httpx.Response(
        status_code=200,
        json={"id": "sub_cancel_1", "status": "cancelled"},
        request=httpx.Request(
            "POST", "https://api.razorpay.com/v1/subscriptions/sub_cancel_1/cancel"
        ),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = fake_cancel_response
        await razorpay.cancel_subscription("sub_cancel_1")

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.razorpay.com/v1/subscriptions/sub_cancel_1/cancel"
        assert kwargs["auth"] == (KEY_ID, KEY_SECRET)
        assert kwargs["json"] == {"cancel_at_cycle_end": 0}


@pytest.mark.asyncio
async def test_razorpay_unknown_account_and_bad_payload(client: AsyncClient, hosted_razorpay):
    # Unknown user
    raw = _rzp_event("subscription.activated", uuid.uuid4())
    res_unknown = await _post_rzp(client, raw)
    assert res_unknown.status_code == 200
    assert res_unknown.json()["status"] == "unknown_user"

    # Bad payload (invalid JSON)
    res_bad = await _post_rzp(client, b"not-a-json")
    assert res_bad.status_code == 400
