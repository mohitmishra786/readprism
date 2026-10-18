"""Email verification and per-domain signup limits on hosted (#175)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.digest import Digest
from app.models.user import User
from app.services import email_verification as ev


@pytest.fixture
def hosted(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "deployment_mode", "hosted")
    monkeypatch.setattr(get_settings(), "registration_mode", "open")


@pytest.fixture
def outbox(monkeypatch):
    sent: list[dict] = []

    async def fake_send(**kwargs):
        sent.append(kwargs)
        return True

    monkeypatch.setattr("app.utils.email.send_email", fake_send)
    return sent


def _token(mail: dict) -> str:
    return mail["html_body"].split("token=")[1].split('"')[0]


async def _register(client: AsyncClient, email: str | None = None):
    data = {"email": email or f"ev{uuid.uuid4().hex[:8]}@example.com", "password": "TestPass123!"}
    resp = await client.post("/api/v1/auth/register", json=data)
    return resp, data["email"]


@pytest.mark.asyncio
async def test_selfhost_needs_no_verification(client, outbox):
    resp, _ = await _register(client)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert me["email_verified"] is True
    assert outbox == []


@pytest.mark.asyncio
async def test_hosted_signup_sends_only_the_verification_email_until_confirmed(
    client, db_session, hosted, outbox
):
    resp, email = await _register(client)
    assert resp.status_code == 201
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    assert [m["to"] for m in outbox] == [email]
    assert "Confirm" in outbox[0]["subject"]
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()["email_verified"] is False

    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    digest = Digest(user_id=user.id, total_items=0)
    db_session.add(digest)
    await db_session.commit()

    from app.services.digest.delivery import deliver_digest

    with patch("app.services.digest.delivery.send_email", AsyncMock(return_value=True)) as send:
        assert await deliver_digest(digest, user, db_session) is False
        send.assert_not_awaited()
    assert ev.may_email(user) is False
    assert await ev.may_receive_newsletters(db_session, user.id) is False

    ok = await client.post("/api/v1/auth/verify-email", json={"token": _token(outbox[0])})
    assert ok.status_code == 200 and ok.json() == {"verified": True}
    # Idempotent: the same link again still succeeds.
    assert (
        await client.post("/api/v1/auth/verify-email", json={"token": _token(outbox[0])})
    ).status_code == 200

    await db_session.refresh(user)
    assert user.email_verified_at is not None
    assert ev.may_email(user) and await ev.may_receive_newsletters(db_session, user.id)
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()["email_verified"] is True


@pytest.mark.asyncio
async def test_bad_tokens_are_rejected(client, db_session, hosted, outbox):
    _, email = await _register(client)
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()

    expired = ev.make_token(user, now=datetime.now(UTC) - timedelta(days=30))
    assert (
        await client.post("/api/v1/auth/verify-email", json={"token": expired})
    ).status_code == 400
    assert (
        await client.post("/api/v1/auth/verify-email", json={"token": "junk"})
    ).status_code == 400

    # A link for the old address stops working after the email changes.
    token = ev.make_token(user)
    user.email = f"changed-{email}"
    await db_session.commit()
    assert (
        await client.post("/api/v1/auth/verify-email", json={"token": token})
    ).status_code == 400
    await db_session.refresh(user)
    assert user.email_verified_at is None


@pytest.mark.asyncio
async def test_magic_link_sign_in_verifies_the_address(client, db_session, hosted, outbox):
    email = f"mlv{uuid.uuid4().hex[:8]}@example.com"
    assert (
        await client.post("/api/v1/auth/magic-link/request", json={"email": email})
    ).status_code == 202
    token = _token(outbox[-1])
    assert (
        await client.post("/api/v1/auth/magic-link/verify", json={"token": token})
    ).status_code == 200
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    assert user.email_verified_at is not None


@pytest.mark.asyncio
async def test_resend_is_throttled_per_account(client, hosted, outbox):
    resp, _ = await _register(client)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    store: set[str] = set()

    async def nx(key, value, ttl_seconds):
        if key in store:
            return False
        store.add(key)
        return True

    with patch("app.utils.cache.cache_set_nx", nx):
        for _ in range(3):
            r = await client.post("/api/v1/auth/verify-email/resend", headers=headers)
            assert r.status_code == 202
    assert len(outbox) == 2  # signup + one resend


@pytest.mark.asyncio
async def test_unverified_newsletter_recipient_is_ignored(client, db_session, hosted, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "app_env", "development")
    monkeypatch.setattr(get_settings(), "mailgun_webhook_signing_key", "")
    user = User(email=f"nl{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.commit()

    with patch("app.api.newsletter.process_inbound_email", AsyncMock()) as process:
        r = await client.post(
            "/api/v1/newsletter/inbound",
            data={
                "sender": "list@news.example",
                "subject": "Issue 1",
                "body-plain": "hello",
                "recipient": f"user-{user.id}@in.example",
            },
        )
    assert r.status_code == 200 and r.json()["status"] == "ignored"
    process.assert_not_awaited()


@pytest.mark.asyncio
async def test_per_domain_signup_limit(client, db_session, hosted, outbox, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "signup_per_domain_per_hour", 2)
    for i in range(2):
        db_session.add(
            User(email=f"bulk{i}-{uuid.uuid4().hex[:4]}@corp.example", hashed_password="x")
        )
    # Old signups from the domain don't count.
    db_session.add(
        User(
            email=f"old-{uuid.uuid4().hex[:4]}@other.example",
            hashed_password="x",
            created_at=datetime.now(UTC) - timedelta(hours=3),
        )
    )
    await db_session.commit()

    resp, _ = await _register(client, f"third-{uuid.uuid4().hex[:4]}@corp.example")
    assert resp.status_code == 429
    resp, _ = await _register(client, f"ok-{uuid.uuid4().hex[:4]}@other.example")
    assert resp.status_code == 201
    # Big providers get a much higher ceiling.
    for i in range(3):
        db_session.add(User(email=f"g{i}-{uuid.uuid4().hex[:4]}@gmail.com", hashed_password="x"))
    await db_session.commit()
    assert await ev.domain_signup_allowed(db_session, "new@gmail.com")


@pytest.mark.asyncio
async def test_selfhost_has_no_domain_limit(db_session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "signup_per_domain_per_hour", 1)
    db_session.add(User(email="a@corp.example", hashed_password="x"))
    await db_session.commit()
    assert await ev.domain_signup_allowed(db_session, "b@corp.example")
