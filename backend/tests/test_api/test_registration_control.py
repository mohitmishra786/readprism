"""Who may register on an instance (#153)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.services import registration


def _creds(**extra) -> dict:
    return {"email": f"r{uuid.uuid4().hex[:8]}@example.com", "password": "TestPass123!", **extra}


@pytest.fixture
def mode(monkeypatch):
    def set_mode(value: str, *, deployment: str = "selfhost", codes: str = "") -> None:
        s = registration.get_settings()
        monkeypatch.setattr(s, "registration_mode", value)
        monkeypatch.setattr(s, "deployment_mode", deployment)
        monkeypatch.setattr(s, "registration_invite_codes", codes)

    return set_mode


def test_defaults_closed_on_selfhost_open_on_hosted(mode):
    mode("")
    assert registration.effective_mode() == "closed"
    mode("", deployment="hosted")
    assert registration.effective_mode() == "open"


@pytest.mark.asyncio
async def test_closed_allows_only_the_first_account(client: AsyncClient, mode):
    mode("closed")
    first = await client.post("/api/v1/auth/register", json=_creds())
    second = await client.post("/api/v1/auth/register", json=_creds())
    assert first.status_code == 201
    assert second.status_code == 403
    assert "closed" in second.json()["detail"].lower()
    state = (await client.get("/api/v1/auth/registration")).json()
    assert state == {
        "mode": "closed",
        "open": False,
        "invite_required": False,
        "first_account": False,
        "hosted": False,
    }


@pytest.mark.asyncio
async def test_invite_mode_needs_a_valid_code(client: AsyncClient, mode):
    mode("invite", codes="alpha-123, beta-456")
    await client.post("/api/v1/auth/register", json=_creds())  # owner
    assert (await client.get("/api/v1/auth/registration")).json()["invite_required"] is True

    missing = await client.post("/api/v1/auth/register", json=_creds())
    wrong = await client.post("/api/v1/auth/register", json=_creds(invite_code="nope"))
    good = await client.post("/api/v1/auth/register", json=_creds(invite_code="beta-456"))
    assert missing.status_code == 403 and wrong.status_code == 403
    assert good.status_code == 201


@pytest.mark.asyncio
async def test_magic_link_never_creates_accounts_when_closed(client: AsyncClient, mode, db_session):
    from sqlalchemy import func, select

    from app.models.user import User

    mode("closed")
    await client.post("/api/v1/auth/register", json=_creds())
    before = (await db_session.execute(select(func.count(User.id)))).scalar()

    with patch("app.utils.email.send_email", new=AsyncMock()) as send:
        resp = await client.post(
            "/api/v1/auth/magic-link/request", json={"email": "stranger@example.com"}
        )

    after = (await db_session.execute(select(func.count(User.id)))).scalar()
    assert resp.status_code == 202 and resp.json() == {"status": "sent"}  # same answer as always
    assert after == before
    send.assert_not_called()


@pytest.mark.asyncio
async def test_open_mode_lets_anyone_register(client: AsyncClient, mode):
    mode("open")
    for _ in range(3):
        assert (await client.post("/api/v1/auth/register", json=_creds())).status_code == 201
