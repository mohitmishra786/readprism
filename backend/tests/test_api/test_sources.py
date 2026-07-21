from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_add_source(client: AsyncClient, test_user_data: dict):
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # sources.py imports _autodiscover_feed into its own namespace, so the patch
    # must target app.api.sources._autodiscover_feed (not the rss_parser module).
    with (
        patch(
            "app.api.sources._autodiscover_feed",
            new=AsyncMock(return_value="https://example.com/feed"),
        ),
        patch("app.workers.tasks.ingest_feeds.ingest_all_feeds.delay"),
    ):
        resp = await client.post(
            "/api/v1/sources",
            json={"url": "https://example.com"},
            headers=headers,
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["url"] == "https://example.com"
    assert data["feed_url"] == "https://example.com/feed"


@pytest.mark.asyncio
async def test_list_sources(client: AsyncClient, test_user_data: dict):
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/sources", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_delete_source(client: AsyncClient, test_user_data: dict):
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with (
        patch("app.api.sources._autodiscover_feed", new=AsyncMock(return_value=None)),
        patch("app.workers.tasks.ingest_feeds.ingest_all_feeds.delay"),
    ):
        add_resp = await client.post(
            "/api/v1/sources",
            json={"url": "https://delete-me.com"},
            headers=headers,
        )
    source_id = add_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/sources/{source_id}", headers=headers)
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_source_health_surfaced(client: AsyncClient, test_user_data: dict, db_session):
    """fetch_error_count is surfaced as a user-facing health status (audit 04-3)."""
    from sqlalchemy import select

    from app.models.source import Source
    from app.models.user import User

    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    token = reg.json()["access_token"]
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()

    db_session.add(Source(user_id=user.id, url="https://ok.com", fetch_error_count=0))
    db_session.add(Source(user_id=user.id, url="https://degraded.com", fetch_error_count=1))
    db_session.add(Source(user_id=user.id, url="https://failing.com", fetch_error_count=5))
    await db_session.commit()

    resp = await client.get("/api/v1/sources", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    health_by_url = {s["url"]: s["health"] for s in resp.json()}
    assert health_by_url["https://ok.com"] == "ok"
    assert health_by_url["https://degraded.com"] == "degraded"
    assert health_by_url["https://failing.com"] == "failing"
