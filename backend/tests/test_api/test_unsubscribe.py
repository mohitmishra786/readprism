"""Digest email unsubscribe flow (audit 08-5)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.user import User
from app.utils.unsubscribe import make_unsubscribe_token


@pytest.mark.asyncio
async def test_unsubscribe_switches_user_to_in_app_only(
    client: AsyncClient, test_user_data: dict, db_session
):
    await client.post("/api/v1/auth/register", json=test_user_data)
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    assert user.digest_frequency != "in_app_only"

    token = make_unsubscribe_token(user.id)
    resp = await client.get(f"/api/v1/digest/unsubscribe?uid={user.id}&token={token}")
    assert resp.status_code == 200
    assert "unsubscribed" in resp.text.lower()

    await db_session.refresh(user)
    assert user.digest_frequency == "in_app_only"


@pytest.mark.asyncio
async def test_unsubscribe_rejects_bad_token(client: AsyncClient, test_user_data: dict, db_session):
    await client.post("/api/v1/auth/register", json=test_user_data)
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    resp = await client.get(f"/api/v1/digest/unsubscribe?uid={user.id}&token=forged")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_unsubscribe_post_one_click(client: AsyncClient, test_user_data: dict, db_session):
    await client.post("/api/v1/auth/register", json=test_user_data)
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    token = make_unsubscribe_token(user.id)
    resp = await client.post(f"/api/v1/digest/unsubscribe?uid={user.id}&token={token}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unsubscribed"
