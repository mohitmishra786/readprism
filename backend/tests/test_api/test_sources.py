from __future__ import annotations

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_add_source(client: AsyncClient, test_user_data: dict):
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.services.ingestion.rss_parser._autodiscover_feed", return_value="https://example.com/feed"),          patch("app.workers.tasks.ingest_feeds.ingest_all_feeds.delay"):
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

    with patch("app.services.ingestion.rss_parser._autodiscover_feed", return_value=None),          patch("app.workers.tasks.ingest_feeds.ingest_all_feeds.delay"):
        add_resp = await client.post(
            "/api/v1/sources",
            json={"url": "https://delete-me.com"},
            headers=headers,
        )
    source_id = add_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/sources/{source_id}", headers=headers)
    assert del_resp.status_code == 204
