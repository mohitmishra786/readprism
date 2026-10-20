"""Account deletion cancels billing and confirms erasure (#221)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models.billing import BillingEvent
from app.models.user import User
from app.services import alerts
from app.services.billing import lemonsqueezy, paddle


@pytest.fixture
def hosted(monkeypatch):
    s = get_settings()
    for key, value in {
        "deployment_mode": "hosted",
        "registration_mode": "open",
        "email_verification": "off",
        "billing_provider": "paddle",
        "billing_api_key": "key_test",
        "billing_sandbox": True,
    }.items():
        monkeypatch.setattr(s, key, value)


async def _paying(client, db_session, provider="paddle"):
    email = f"del{uuid.uuid4().hex[:6]}@example.com"
    reg = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "TestPass123!"}
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.tier, user.billing_status = "reader", "active"
    user.billing_provider, user.billing_subscription_id = provider, f"sub_{uuid.uuid4().hex[:8]}"
    await db_session.commit()
    return user, headers


@pytest.mark.asyncio
async def test_paddle_and_lemonsqueezy_cancel_requests(hosted):
    calls = []

    async def fake_post(self, url, json=None, headers=None):
        calls.append(("POST", url, json, headers["Authorization"]))
        return httpx.Response(200, request=httpx.Request("POST", url))

    async def fake_delete(self, url, headers=None):
        calls.append(("DELETE", url, None, headers["Authorization"]))
        return httpx.Response(200, request=httpx.Request("DELETE", url))

    with patch("httpx.AsyncClient.post", fake_post), patch("httpx.AsyncClient.delete", fake_delete):
        await paddle.cancel_subscription("sub_1")
        await lemonsqueezy.cancel_subscription("42")
    assert calls == [
        (
            "POST",
            "https://sandbox-api.paddle.com/subscriptions/sub_1/cancel",
            {"effective_from": "immediately"},
            "Bearer key_test",
        ),
        ("DELETE", "https://api.lemonsqueezy.com/v1/subscriptions/42", None, "Bearer key_test"),
    ]


@pytest.mark.asyncio
async def test_deleting_a_paying_account_cancels_then_erases_and_confirms(
    client, db_session, hosted
):
    user, headers = await _paying(client, db_session)
    uid, email, sub = user.id, user.email, user.billing_subscription_id
    cancel, send = AsyncMock(), AsyncMock(return_value=True)
    with (
        patch.object(paddle, "cancel_subscription", cancel),
        patch("app.utils.email.send_email", send),
    ):
        assert (await client.delete("/api/v1/account", headers=headers)).status_code == 204
    cancel.assert_awaited_once_with(sub)
    db_session.expire_all()
    assert await db_session.get(User, uid) is None
    event = (
        await db_session.execute(
            select(BillingEvent).where(BillingEvent.key == f"paddle:deletion-cancel:{sub}")
        )
    ).scalar_one()
    assert event.outcome == f"cancelled: subscription {sub}" and event.user_id is None
    mail = send.await_args.kwargs
    assert mail["to"] == email and "won't be charged again" in mail["text_body"]


@pytest.mark.asyncio
async def test_failed_cancel_still_erases_and_tells_the_operator(client, db_session, hosted):
    user, headers = await _paying(client, db_session, provider="lemonsqueezy")
    uid, sub = user.id, user.billing_subscription_id
    send = AsyncMock(return_value=True)
    with (
        patch.object(
            lemonsqueezy, "cancel_subscription", AsyncMock(side_effect=RuntimeError("502"))
        ),
        patch("app.utils.email.send_email", send),
    ):
        assert (await client.delete("/api/v1/account", headers=headers)).status_code == 204
    db_session.expire_all()
    assert await db_session.get(User, uid) is None
    assert "couldn't cancel" in send.await_args.kwargs["text_body"]
    assert send.await_count == 1  # the user only; the operator learns through alerts

    with patch("app.services.instance_health.check", AsyncMock(return_value=[])):
        found = await alerts.evaluate(
            db_session, redis=_EmptyRedis(), queue_report=lambda *a, **k: _empty_report()
        )
    billing_alert = [a for a in found if a.key == "billing_cancel_failed"]
    assert billing_alert and sub in billing_alert[0].message


@pytest.mark.asyncio
async def test_no_subscription_means_no_cancel_call(client, db_session, hosted):
    email = f"free{uuid.uuid4().hex[:6]}@example.com"
    reg = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "TestPass123!"}
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    cancel = AsyncMock()
    with (
        patch.object(paddle, "cancel_subscription", cancel),
        patch("app.utils.email.send_email", AsyncMock(return_value=True)),
    ):
        assert (await client.delete("/api/v1/account", headers=headers)).status_code == 204
    cancel.assert_not_awaited()


class _EmptyRedis:
    async def get(self, key):
        return None


def _empty_report():
    return {
        "queue_wait_seconds": {},
        "task_runtime_seconds": {},
        "digest_delivery": {"on_time_ratio": None, "lateness_seconds": {"count": 0}},
    }
