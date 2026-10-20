"""Help readers unsubscribe from the original inbox (#249)."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ingestion.newsletter import delivery_of
from app.services.ingestion.newsletter_parse import unsubscribe_options

SECRET = "pm-secret"


def test_only_safe_unsubscribe_links_are_kept():
    header = "<mailto:leave@news.example?subject=unsubscribe>, <https://news.example/u/abc>"
    assert unsubscribe_options(header) == {
        "url": "https://news.example/u/abc",
        "mailto": "mailto:leave@news.example?subject=unsubscribe",
    }
    assert unsubscribe_options("<javascript:alert(1)>, <http://news.example/u>") is None
    assert unsubscribe_options(None) is None


def test_direct_vs_forwarded():
    assert delivery_of("u.abc123@in.example.com") == "direct"
    assert delivery_of("Ada <ada@gmail.com>") == "forwarded"


async def _setup(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "newsletter_domain", "in.example.com")
    monkeypatch.setattr(get_settings(), "postmark_webhook_secret", SECRET)
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": f"un{uuid.uuid4().hex[:6]}@example.com", "password": "TestPass123!"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    address = (await client.get("/api/v1/newsletter/address", headers=headers)).json()["address"]
    return headers, address


async def _deliver(client, payload: dict):
    body = json.dumps(
        {"MessageID": f"m-{uuid.uuid4().hex}", "TextBody": "hello", **payload}
    ).encode()
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    with patch("app.api.newsletter.process_inbound_email", AsyncMock()):
        resp = await client.post(
            "/api/v1/newsletter/inbound/postmark",
            content=body,
            headers={"x-webhook-signature": sig, "Content-Type": "application/json"},
        )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_sender_list_shows_unsubscribe_actions(client, monkeypatch):
    headers, address = await _setup(client, monkeypatch)
    await _deliver(
        client,
        {
            "From": "Weekly Rust <news@rust.example>",
            "To": "reader@gmail.com",
            "OriginalRecipient": address,
            "Subject": "Issue 1",
            "Headers": [{"Name": "List-Unsubscribe", "Value": "<https://rust.example/unsub/r1>"}],
        },
    )
    await _deliver(
        client, {"From": "DB Digest <hi@db.example>", "To": address, "Subject": "Issue 9"}
    )

    sources = {s["name"]: s for s in (await client.get("/api/v1/sources", headers=headers)).json()}
    rust = sources["Weekly Rust <news@rust.example>"]
    assert rust["newsletter_delivery"] == "forwarded"
    assert rust["unsubscribe_options"] == {"url": "https://rust.example/unsub/r1", "mailto": None}
    db = sources["DB Digest <hi@db.example>"]
    assert db["newsletter_delivery"] == "direct" and db["unsubscribe_options"] is None

    # A later issue refreshes the sender's link.
    await _deliver(
        client,
        {
            "From": "Weekly Rust <news@rust.example>",
            "To": "reader@gmail.com",
            "OriginalRecipient": address,
            "Subject": "Issue 2",
            "Headers": [{"Name": "List-Unsubscribe", "Value": "<mailto:stop@rust.example>"}],
        },
    )
    sources = {s["name"]: s for s in (await client.get("/api/v1/sources", headers=headers)).json()}
    assert sources["Weekly Rust <news@rust.example>"]["unsubscribe_options"] == {
        "url": None,
        "mailto": "mailto:stop@rust.example",
    }


@pytest.mark.asyncio
async def test_mailgun_path_records_the_sender_link(client, monkeypatch):
    from app.config import get_settings

    headers, address = await _setup(client, monkeypatch)
    monkeypatch.setattr(get_settings(), "mailgun_webhook_signing_key", "")
    monkeypatch.setattr(get_settings(), "app_env", "development")  # unsigned dev mode
    form = {
        "sender": "Grid Notes <news@grid.example>",
        "recipient": address,
        "To": "reader@outlook.com",
        "subject": "Issue 3",
        "body-plain": "hello",
        "Message-Id": f"<{uuid.uuid4().hex}@grid>",
        "message-headers": json.dumps([["List-Unsubscribe", "<https://grid.example/stop>"]]),
    }
    with (
        patch("app.api.newsletter.process_inbound_email", AsyncMock()),
        patch(
            "app.services.email_verification.may_receive_newsletters", AsyncMock(return_value=True)
        ),
    ):
        resp = await client.post("/api/v1/newsletter/inbound", data=form)
    assert resp.status_code == 200, resp.text
    sources = {s["name"]: s for s in (await client.get("/api/v1/sources", headers=headers)).json()}
    grid = sources["Grid Notes <news@grid.example>"]
    assert grid["newsletter_delivery"] == "forwarded"
    assert grid["unsubscribe_options"] == {"url": "https://grid.example/stop", "mailto": None}
