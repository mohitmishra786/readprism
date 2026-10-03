"""Extension save & rate (EC-02): private items, strong signals, token scopes."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User


@pytest.mark.asyncio
async def test_save_and_rate_creates_private_strong_signal(
    client: AsyncClient, test_user_data: dict, db_session
):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    jwt = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    created = await client.post(
        "/api/v1/tokens", json={"name": "ext", "scopes": ["read", "write"]}, headers=jwt
    )
    tok = {"Authorization": f"Bearer {created.json()['token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()

    result = await client.post(
        "/api/v1/extension/save",
        json={"url": "https://saved-page.example/article", "title": "Great read", "rating": 1},
        headers=tok,
    )
    assert result.status_code == 201

    item = (
        await db_session.execute(
            select(ContentItem).where(ContentItem.url == "https://saved-page.example/article")
        )
    ).scalar_one()
    assert item.origin == "extension"
    assert item.owner_user_id == user.id  # private — never in another user's pool

    interaction = (
        await db_session.execute(
            select(UserContentInteraction).where(
                UserContentInteraction.user_id == user.id,
                UserContentInteraction.content_item_id == item.id,
            )
        )
    ).scalar_one()
    assert interaction.saved is True
    assert interaction.explicit_rating == 1  # strong signal

    # Idempotent re-save with a different rating updates in place.
    again = await client.post(
        "/api/v1/extension/save",
        json={"url": "https://saved-page.example/article", "title": "Great read", "rating": -1},
        headers=tok,
    )
    assert again.status_code == 201
    await db_session.refresh(interaction)
    assert interaction.explicit_rating == -1


@pytest.mark.asyncio
async def test_readonly_token_cannot_save(client: AsyncClient, test_user_data: dict):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    jwt = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    created = await client.post(
        "/api/v1/tokens", json={"name": "ro", "scopes": ["read"]}, headers=jwt
    )
    tok = {"Authorization": f"Bearer {created.json()['token']}"}

    denied = await client.post(
        "/api/v1/extension/save",
        json={"url": "https://x.example/a", "title": "x"},
        headers=tok,
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_bad_rating_is_rejected(client: AsyncClient, test_user_data: dict):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    jwt = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    bad = await client.post(
        "/api/v1/extension/save",
        json={"url": "https://x.example/a", "title": "x", "rating": 5},
        headers=jwt,
    )
    assert bad.status_code == 422
