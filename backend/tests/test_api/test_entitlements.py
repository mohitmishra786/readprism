"""Tier entitlement enforcement (audit 13-1/13-5)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.source import Source
from app.models.user import User
from app.services import entitlements


@pytest.mark.asyncio
async def test_free_user_blocked_at_source_limit(
    client: AsyncClient, test_user_data: dict, db_session, monkeypatch
):
    monkeypatch.setattr(entitlements.settings, "free_max_sources", 2)
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    token = reg.json()["access_token"]
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()

    # Seed two sources (at the limit).
    db_session.add_all(
        [
            Source(user_id=user.id, url="https://a.com"),
            Source(user_id=user.id, url="https://b.com"),
        ]
    )
    await db_session.commit()

    with (
        patch("app.api.sources._autodiscover_feed", new=AsyncMock(return_value=None)),
        patch("app.workers.tasks.ingest_feeds.ingest_all_feeds.delay"),
    ):
        resp = await client.post(
            "/api/v1/sources",
            json={"url": "https://c.com"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 402


@pytest.mark.asyncio
async def test_pro_user_unlimited_sources(
    client: AsyncClient, test_user_data: dict, db_session, monkeypatch
):
    monkeypatch.setattr(entitlements.settings, "free_max_sources", 1)
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    token = reg.json()["access_token"]
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    user.tier = "pro"
    db_session.add(Source(user_id=user.id, url="https://a.com"))
    await db_session.commit()

    with (
        patch("app.api.sources._autodiscover_feed", new=AsyncMock(return_value=None)),
        patch("app.workers.tasks.ingest_feeds.ingest_all_feeds.delay"),
    ):
        resp = await client.post(
            "/api/v1/sources",
            json={"url": "https://c.com"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
