"""Per-user private (newsletter) content segregation (audit 06-6)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.content import ContentItem
from app.models.user import User


async def _register(client: AsyncClient, email: str) -> str:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "TestPass123!", "display_name": "U"},
    )
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_private_content_readable_only_by_owner(client: AsyncClient, db_session):
    owner_token = await _register(client, "owner@example.com")
    other_token = await _register(client, "other@example.com")

    owner = (
        await db_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()

    private = ContentItem(
        url="newsletter://owner/msg-1",
        title="My private newsletter",
        full_text="personalized body with unsubscribe token",
        owner_user_id=owner.id,
    )
    db_session.add(private)
    await db_session.commit()

    # Owner can read it.
    owner_resp = await client.get(
        f"/api/v1/content/{private.id}", headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert owner_resp.status_code == 200
    assert owner_resp.json()["title"] == "My private newsletter"

    # A different user gets 404 (existence not even confirmed).
    other_resp = await client.get(
        f"/api/v1/content/{private.id}", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert other_resp.status_code == 404


@pytest.mark.asyncio
async def test_public_content_readable_by_any_user(client: AsyncClient, db_session):
    token = await _register(client, "reader@example.com")
    public = ContentItem(
        url="https://example.com/public-article",
        title="Public article",
        owner_user_id=None,
    )
    db_session.add(public)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/content/{public.id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
