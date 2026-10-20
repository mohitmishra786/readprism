"""Newsletters forwarded from the reader's inbox reach them (#322)."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ingestion.newsletter_parse import parse_postmark, parse_rfc822

SECRET = "pm-secret"


def test_postmark_matches_the_envelope_and_keeps_the_header():
    parsed = parse_postmark(
        {
            "From": "news@x.example",
            "To": "ada@gmail.com",
            "OriginalRecipient": "u.abc123@in.example.com",
            "Subject": "Issue 1",
            "TextBody": "hi",
        }
    )
    assert parsed.recipient == "u.abc123@in.example.com" and parsed.header_to == "ada@gmail.com"
    direct = parse_postmark(
        {"From": "news@x.example", "To": "u.abc123@in.example.com", "Subject": "s", "TextBody": "t"}
    )
    assert direct.recipient == direct.header_to == "u.abc123@in.example.com"


def test_raw_email_uses_delivered_to():
    raw = (
        "From: news@x.example\r\nTo: ada@gmail.com\r\nDelivered-To: u.abc123@in.example.com\r\n"
        "Subject: Issue 2\r\nMessage-ID: <m2@x>\r\n\r\nhello"
    )
    parsed = parse_rfc822(raw)
    assert parsed.recipient == "u.abc123@in.example.com" and parsed.header_to == "ada@gmail.com"


@pytest.mark.asyncio
async def test_a_forwarded_newsletter_reaches_the_reader(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "newsletter_domain", "in.example.com")
    monkeypatch.setattr(get_settings(), "postmark_webhook_secret", SECRET)
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": f"fw{uuid.uuid4().hex[:6]}@example.com", "password": "TestPass123!"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    address = (await client.get("/api/v1/newsletter/address", headers=headers)).json()["address"]
    payload = json.dumps(
        {
            "From": "news@letter.example",
            "To": "reader@gmail.com",
            "OriginalRecipient": address,
            "Subject": "Issue 12",
            "MessageID": f"m-{uuid.uuid4().hex}",
            "TextBody": "hello",
        }
    ).encode()
    sig = hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()
    with patch("app.api.newsletter.process_inbound_email", AsyncMock()) as store:
        await client.post(
            "/api/v1/newsletter/inbound/postmark",
            content=payload,
            headers={"x-webhook-signature": sig, "Content-Type": "application/json"},
        )
    assert store.await_args.kwargs["user_id"] is not None
