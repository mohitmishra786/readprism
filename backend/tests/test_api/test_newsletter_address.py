"""Personal newsletter address with a live test (#151)."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

SECRET = "pm-secret"


@pytest.fixture
def inbound_on(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "newsletter_domain", "in.example.com")
    monkeypatch.setattr(get_settings(), "postmark_webhook_secret", SECRET)


async def _login(client):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": f"nl{uuid.uuid4().hex[:6]}@example.com", "password": "TestPass123!"},
    )
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@pytest.mark.asyncio
async def test_address_is_created_once_and_stays_the_same(client):
    headers = await _login(client)
    first = (await client.get("/api/v1/newsletter/address", headers=headers)).json()
    again = (await client.get("/api/v1/newsletter/address", headers=headers)).json()
    assert first["address"] == again["address"]
    assert first["address"].startswith("u.") and first["inbound_configured"] is False


@pytest.mark.asyncio
async def test_test_email_round_trip_is_seen_and_not_stored(client, inbound_on):
    headers = await _login(client)
    address = (await client.get("/api/v1/newsletter/address", headers=headers)).json()["address"]
    assert address.endswith("@in.example.com")

    outbox: list[dict] = []

    async def fake_send(**kwargs):
        outbox.append(kwargs)
        return True

    with patch("app.utils.email.send_email", fake_send):
        sent = await client.post("/api/v1/newsletter/address/test", headers=headers)
    assert sent.status_code == 202 and outbox[0]["to"] == address
    waiting = (await client.get("/api/v1/newsletter/address/test", headers=headers)).json()
    assert waiting["status"] == "waiting"

    # The provider delivers it back to the inbound webhook.
    payload = json.dumps(
        {
            "From": "noreply@weirling.example",
            "To": address,
            "Subject": outbox[0]["subject"],
            "MessageID": f"m-{uuid.uuid4().hex}",
            "TextBody": "test",
        }
    ).encode()
    signature = hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()
    with patch("app.api.newsletter.process_inbound_email", AsyncMock()) as store:
        resp = await client.post(
            "/api/v1/newsletter/inbound/postmark",
            content=payload,
            headers={"x-webhook-signature": signature, "Content-Type": "application/json"},
        )
    assert resp.json()["status"] == "test_received"
    store.assert_not_awaited()  # the marker is not filed as a newsletter
    done = (await client.get("/api/v1/newsletter/address/test", headers=headers)).json()
    assert done["status"] == "received" and done["received_at"]


@pytest.mark.asyncio
async def test_real_newsletters_to_the_address_reach_the_user(client, inbound_on):
    headers = await _login(client)
    address = (await client.get("/api/v1/newsletter/address", headers=headers)).json()["address"]
    payload = json.dumps(
        {
            "From": "news@letter.example",
            "To": address,
            "Subject": "Issue 12",
            "MessageID": f"m-{uuid.uuid4().hex}",  # unique: the webhook drops replays
            "TextBody": "hello",
        }
    ).encode()
    signature = hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()
    with patch("app.api.newsletter.process_inbound_email", AsyncMock()) as store:
        await client.post(
            "/api/v1/newsletter/inbound/postmark",
            content=payload,
            headers={"x-webhook-signature": signature, "Content-Type": "application/json"},
        )
    assert store.await_args.kwargs["user_id"] is not None


@pytest.mark.asyncio
async def test_test_needs_inbound_configured(client):
    headers = await _login(client)
    resp = await client.post("/api/v1/newsletter/address/test", headers=headers)
    assert resp.status_code == 409
