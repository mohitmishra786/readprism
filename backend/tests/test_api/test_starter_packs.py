"""Starter packs (CS-02): bundles, subscribe, liveness gate."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.source import Source
from app.models.user import User
from app.services.cold_start.starter_packs import list_starter_packs


def test_at_least_twenty_packs_with_ten_to_twenty_five_feeds():
    packs = list_starter_packs()
    assert len(packs) >= 20
    for pack in packs:
        assert 10 <= len(pack.feeds) <= 25, f"{pack.id} has {len(pack.feeds)} feeds"
        for feed in pack.feeds:
            assert feed["url"].startswith("https://"), f"{pack.id}: {feed['url']}"
            assert feed["name"]


@pytest.mark.asyncio
async def test_subscribe_pack_is_idempotent(client: AsyncClient, test_user_data: dict, db_session):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()

    result = await client.post(
        "/api/v1/sources/starter-packs/security-privacy/subscribe", headers=headers
    )
    assert result.status_code == 200
    body = result.json()
    assert body["subscribed"] == 10  # the security pack ships 10 feeds
    assert body["subscribed"] >= 10

    count = len(
        (await db_session.execute(select(Source).where(Source.user_id == user.id))).scalars().all()
    )
    assert count == body["subscribed"]

    # Second subscribe adds nothing.
    again = await client.post(
        "/api/v1/sources/starter-packs/security-privacy/subscribe", headers=headers
    )
    assert again.json()["subscribed"] == 0
    assert again.json()["already_had"] == body["subscribed"]


@pytest.mark.asyncio
async def test_unknown_pack_is_404(client: AsyncClient, test_user_data: dict):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    result = await client.post("/api/v1/sources/starter-packs/nope/subscribe", headers=headers)
    assert result.status_code == 404
