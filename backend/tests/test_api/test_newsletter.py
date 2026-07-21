"""Tests for the inbound newsletter webhook + Mailgun signature auth (audit 06-1)."""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest
from httpx import AsyncClient

from app.api import newsletter as newsletter_api
from app.services.ingestion.newsletter import verify_mailgun_signature

SIGNING_KEY = "test-webhook-signing-key"


def _sign(token: str, timestamp: str, key: str = SIGNING_KEY) -> str:
    return hmac.new(
        key=key.encode(), msg=f"{timestamp}{token}".encode(), digestmod=hashlib.sha256
    ).hexdigest()


def test_verify_valid_signature():
    ts, tok = str(int(time.time())), "abc123"
    assert verify_mailgun_signature(
        token=tok, timestamp=ts, signature=_sign(tok, ts), signing_key=SIGNING_KEY
    )


def test_verify_rejects_tampered_signature():
    ts, tok = str(int(time.time())), "abc123"
    assert not verify_mailgun_signature(
        token=tok, timestamp=ts, signature="deadbeef", signing_key=SIGNING_KEY
    )


def test_verify_rejects_stale_timestamp():
    ts = str(int(time.time()) - 5000)
    tok = "abc123"
    assert not verify_mailgun_signature(
        token=tok,
        timestamp=ts,
        signature=_sign(tok, ts),
        signing_key=SIGNING_KEY,
        max_age_seconds=900,
    )


def test_verify_rejects_missing_fields():
    assert not verify_mailgun_signature(
        token="", timestamp="", signature="", signing_key=SIGNING_KEY
    )


@pytest.mark.asyncio
async def test_webhook_rejects_unauthenticated_in_production(client: AsyncClient, monkeypatch):
    """No signing key + non-dev env => fail closed (401)."""
    monkeypatch.setattr(newsletter_api.settings, "mailgun_webhook_signing_key", "")
    monkeypatch.setattr(newsletter_api.settings, "app_env", "production")
    resp = await client.post(
        "/api/v1/newsletter/inbound",
        data={"sender": "a@b.com", "subject": "Hi", "body-plain": "hello", "recipient": "user-x@i"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_signature(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(newsletter_api.settings, "mailgun_webhook_signing_key", SIGNING_KEY)
    monkeypatch.setattr(newsletter_api.settings, "app_env", "production")
    ts, tok = str(int(time.time())), "tok-invalid"
    resp = await client.post(
        "/api/v1/newsletter/inbound",
        data={
            "sender": "a@b.com",
            "subject": "Hi",
            "body-plain": "hello",
            "recipient": "user-x@i",
            "token": tok,
            "timestamp": ts,
            "signature": "not-the-real-signature",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_accepts_valid_signature_and_blocks_replay(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(newsletter_api.settings, "mailgun_webhook_signing_key", SIGNING_KEY)
    monkeypatch.setattr(newsletter_api.settings, "app_env", "production")
    ts, tok = str(int(time.time())), f"tok-{int(time.time() * 1000)}"
    data = {
        "sender": "a@b.com",
        "subject": "Hi",
        "body-plain": "hello world",
        "recipient": "user-abc@inbox",
        "token": tok,
        "timestamp": ts,
        "signature": _sign(tok, ts),
    }
    resp = await client.post("/api/v1/newsletter/inbound", data=data)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Same token replayed => rejected.
    replay = await client.post("/api/v1/newsletter/inbound", data=data)
    assert replay.status_code == 409
