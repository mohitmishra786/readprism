"""Discover-sources (EC-06): mining, accept, dismissal permanence."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.source import Source
from app.models.suggestion import SourceSuggestion
from app.models.user import User


@pytest.mark.asyncio
async def test_discovery_reads_suggest_their_source(
    client: AsyncClient, test_user_data: dict, db_session
):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    other = User(email="ec6-pub@example.com", hashed_password="x")
    db_session.add(other)
    await db_session.flush()

    pub = Source(user_id=other.id, url="https://ec6-pub.example/feed", name="Pub Feed")
    own = Source(user_id=user.id, url="https://ec6-own.example/feed")
    db_session.add_all([pub, own])
    await db_session.flush()
    item = ContentItem(
        source_id=pub.id,
        url="https://ec6-pub.example/read",
        title="Loved this",
        origin="discovery",
        fetched_at=datetime.now(UTC),
    )
    db_session.add(item)
    await db_session.flush()
    db_session.add(
        UserContentInteraction(user_id=user.id, content_item_id=item.id, read_completion_pct=0.95)
    )
    await db_session.commit()

    listed = await client.get("/api/v1/sources/discover-suggestions", headers=headers)
    assert listed.status_code == 200
    suggestions = listed.json()
    assert any(s["url"] == "https://ec6-pub.example/feed" for s in suggestions)
    target = next(s for s in suggestions if s["url"] == "https://ec6-pub.example/feed")
    assert "Loved this" in target["reason"]


@pytest.mark.asyncio
async def test_dismissal_is_permanent(client: AsyncClient, test_user_data: dict, db_session):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    row = SourceSuggestion(
        user_id=user.id,
        url="https://dismissed.example/feed",
        name="Gone",
        reason="test",
    )
    db_session.add(row)
    await db_session.commit()

    dismissed = await client.post(
        f"/api/v1/sources/discover-suggestions/{row.id}/dismiss", headers=headers
    )
    assert dismissed.status_code == 200

    # Refresh: the dismissed URL never returns.
    listed = await client.get("/api/v1/sources/discover-suggestions", headers=headers)
    urls = [s["url"] for s in listed.json()]
    assert "https://dismissed.example/feed" not in urls


@pytest.mark.asyncio
async def test_accept_creates_the_source(client: AsyncClient, test_user_data: dict, db_session):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    row = SourceSuggestion(
        user_id=user.id, url="https://acceptme.example/feed", name="Keep", reason="test"
    )
    db_session.add(row)
    await db_session.commit()

    accepted = await client.post(
        f"/api/v1/sources/discover-suggestions/{row.id}/accept", headers=headers
    )
    assert accepted.status_code == 201
    assert accepted.json()["url"] == "https://acceptme.example/feed"

    # Double-accept is a 404 (no longer pending).
    again = await client.post(
        f"/api/v1/sources/discover-suggestions/{row.id}/accept", headers=headers
    )
    assert again.status_code == 404

    sources = {
        s.url
        for s in (
            await db_session.execute(select(Source).where(Source.user_id == user.id))
        ).scalars()
    }
    assert "https://acceptme.example/feed" in sources
