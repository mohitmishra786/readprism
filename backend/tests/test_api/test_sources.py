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
        patch("app.workers.tasks.ingest_feeds.ingest_user_sources.delay"),
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
        patch("app.workers.tasks.ingest_feeds.ingest_user_sources.delay"),
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

    db_session.add(Source(user_id=user.id, url="https://ok.com", feed_status="healthy"))
    db_session.add(
        Source(
            user_id=user.id,
            url="https://degraded.com",
            feed_status="degraded",
            fetch_error_count=1,
            last_error="HTTP 500",
        )
    )
    db_session.add(
        Source(
            user_id=user.id, url="https://failing.com", feed_status="failing", fetch_error_count=3
        )
    )
    db_session.add(
        Source(user_id=user.id, url="https://dead.com", feed_status="dead", is_active=False)
    )
    await db_session.commit()

    resp = await client.get("/api/v1/sources", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    by_url = {s["url"]: s for s in resp.json()}
    assert by_url["https://ok.com"]["health"] == "healthy"
    assert by_url["https://degraded.com"]["health"] == "degraded"
    assert by_url["https://degraded.com"]["last_error"] == "HTTP 500"
    assert by_url["https://failing.com"]["health"] == "failing"
    assert by_url["https://dead.com"]["health"] == "dead"
    assert by_url["https://ok.com"]["items_per_week"] == 0


@pytest.mark.asyncio
async def test_adding_reddit_url_shows_unsupported_error(client: AsyncClient, test_user_data: dict):
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/sources",
        json={"url": "https://www.reddit.com/r/MachineLearning"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Unsupported: Reddit" in resp.json()["detail"]
    assert "13 Nov 2026" in resp.json()["detail"]


async def _dead_source(client: AsyncClient, test_user_data: dict, db_session):
    import uuid as _uuid

    from sqlalchemy import select

    from app.models.feed import Feed
    from app.models.source import Source
    from app.models.user import User

    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    old_feed = Feed(
        key=f"https://moved.example/old-{_uuid.uuid4().hex[:4]}.xml", url="https://moved.example"
    )
    db_session.add(old_feed)
    await db_session.flush()
    src = Source(
        user_id=user.id,
        url="https://moved.example/blog",
        feed_url=old_feed.key,
        feed_id=old_feed.id,
        is_active=False,
        feed_status="dead",
        fetch_error_count=9,
        last_error="HTTP 410 Gone",
        dead_notice_pending=True,
    )
    db_session.add(src)
    await db_session.commit()
    return headers, src, old_feed


@pytest.mark.asyncio
async def test_fix_moves_a_dead_source_to_its_new_feed(client, test_user_data, db_session):
    """#212: the site now advertises a different feed; one click switches to it."""
    from sqlalchemy import select

    from app.models.feed import Feed
    from app.models.source import Source

    headers, src, old_feed = await _dead_source(client, test_user_data, db_session)
    new_feed = "https://moved.example/feed.xml"
    with (
        patch("app.api.sources._autodiscover_feed", AsyncMock(return_value=new_feed)),
        patch("app.workers.tasks.ingest_feeds.ingest_user_sources.delay") as fetch_now,
    ):
        resp = await client.post(f"/api/v1/sources/{src.id}/fix", headers=headers)

    assert resp.status_code == 200 and resp.json() == {"status": "fixed", "feed_url": new_feed}
    await db_session.refresh(src)
    assert src.feed_url == new_feed and src.is_active and src.feed_status == "healthy"
    assert src.fetch_error_count == 0 and src.last_error is None
    assert not src.dead_notice_pending
    attached = (await db_session.execute(select(Feed).where(Feed.id == src.feed_id))).scalar_one()
    assert attached.key == new_feed and attached.id != old_feed.id
    fetch_now.assert_called_once()
    assert (await db_session.execute(select(Source).where(Source.id == src.id))).scalar_one()


@pytest.mark.asyncio
async def test_fix_without_a_new_feed_suggests_removal(client, test_user_data, db_session):
    headers, src, old_feed = await _dead_source(client, test_user_data, db_session)
    with patch("app.api.sources._autodiscover_feed", AsyncMock(return_value=old_feed.key)):
        resp = await client.post(f"/api/v1/sources/{src.id}/fix", headers=headers)
    assert resp.json()["status"] == "no_new_feed" and resp.json()["suggestion"] == "remove"
    await db_session.refresh(src)
    assert src.feed_status == "dead"
