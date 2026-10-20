"""Acceptance criteria tests for takedown (#183):
- Excluded from digests, search, feed, reader (404), and future ingestion.
- Item disappears for every user immediately after entry added with no restart.
- /contact page setting.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.config import get_settings
from app.models.content import ContentItem, UserContentInteraction
from app.models.source import Source
from app.models.user import User
from app.services.takedown import add_blocked_entry, remove_blocked_entry


@pytest.mark.asyncio
async def test_contact_endpoint_grievance_email(client: AsyncClient, monkeypatch):
    # Hidden when empty
    monkeypatch.setattr(get_settings(), "grievance_contact_email", "")
    resp = await client.get("/api/v1/contact")
    assert resp.status_code == 200
    assert resp.json()["grievance_contact_email"] is None

    # Shown when configured
    monkeypatch.setattr(get_settings(), "grievance_contact_email", "grievance@readprism.example")
    resp = await client.get("/api/v1/contact")
    assert resp.status_code == 200
    assert resp.json()["grievance_contact_email"] == "grievance@readprism.example"


@pytest.mark.asyncio
async def test_item_disappears_for_every_user_immediately_no_restart(
    client: AsyncClient, db_session
):
    """Proves an item disappears for every user right after the entry is added,
    with no restart: reader (404), feed, search, and digest exclusion."""

    # 1. Setup User A and User B via register endpoint
    email_a = f"user-a-{uuid.uuid4().hex[:6]}@example.com"
    email_b = f"user-b-{uuid.uuid4().hex[:6]}@example.com"
    reg_a = await client.post(
        "/api/v1/auth/register", json={"email": email_a, "password": "Password123!"}
    )
    reg_b = await client.post(
        "/api/v1/auth/register", json={"email": email_b, "password": "Password123!"}
    )
    token_a = reg_a.json()["access_token"]
    token_b = reg_b.json()["access_token"]

    user_a = (await db_session.execute(select(User).where(User.email == email_a))).scalar_one()
    user_b = (await db_session.execute(select(User).where(User.email == email_b))).scalar_one()

    # Sources for shared feed
    feed_url = f"https://publisher.example.com/{uuid.uuid4().hex}/feed.xml"
    source_a = Source(
        user_id=user_a.id, name="Shared Feed", url=feed_url, feed_url=feed_url, is_active=True
    )
    source_b = Source(
        user_id=user_b.id, name="Shared Feed", url=feed_url, feed_url=feed_url, is_active=True
    )
    db_session.add_all([source_a, source_b])
    await db_session.flush()

    item_url = f"https://publisher.example.com/articles/dispute-{uuid.uuid4().hex[:8]}"
    item = ContentItem(
        source_id=source_a.id,
        url=item_url,
        title="Disputed Article Subject to Removal",
        full_text="This article will be taken down globally across all instances.",
        word_count=10,
        rankable=True,
        fetched_at=datetime.now(UTC),
        search_tsv=None,
    )
    db_session.add(item)
    await db_session.flush()

    # Interactions for feed / digest ranking
    ia = UserContentInteraction(user_id=user_a.id, content_item_id=item.id, prs_score=0.95)
    ib = UserContentInteraction(user_id=user_b.id, content_item_id=item.id, prs_score=0.92)
    db_session.add_all([ia, ib])
    await db_session.commit()

    # 2. Before takedown: both users see item in reader (200)
    resp_a = await client.get(
        f"/api/v1/content/{item.id}", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp_a.status_code == 200
    assert resp_a.json()["id"] == str(item.id)

    resp_b = await client.get(
        f"/api/v1/content/{item.id}", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp_b.status_code == 200
    assert resp_b.json()["id"] == str(item.id)

    # Both see item in feed
    feed_a = await client.get(
        "/api/v1/content/feed", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert feed_a.status_code == 200
    assert any(fi["content"]["id"] == str(item.id) for fi in feed_a.json())

    feed_b = await client.get(
        "/api/v1/content/feed", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert feed_b.status_code == 200
    assert any(fi["content"]["id"] == str(item.id) for fi in feed_b.json())

    # 3. Add takedown entry into database
    await add_blocked_entry(db_session, item_url, "Copyright infringement notice")
    await db_session.commit()

    # 4. Right after entry is added (with no restart):
    # Reader returns 404 for User A AND User B
    resp_a_after = await client.get(
        f"/api/v1/content/{item.id}", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp_a_after.status_code == 404

    resp_b_after = await client.get(
        f"/api/v1/content/{item.id}", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp_b_after.status_code == 404

    # Feed excludes item for User A AND User B
    feed_a_after = await client.get(
        "/api/v1/content/feed", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert feed_a_after.status_code == 200
    assert not any(fi["content"]["id"] == str(item.id) for fi in feed_a_after.json())

    feed_b_after = await client.get(
        "/api/v1/content/feed", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert feed_b_after.status_code == 200
    assert not any(fi["content"]["id"] == str(item.id) for fi in feed_b_after.json())

    # Search excludes item
    search_res = await client.get(
        "/api/v1/search?q=Disputed", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert search_res.status_code == 200
    assert not any(r["id"] == str(item.id) for r in search_res.json()["hits"])

    # Digest candidate builder excludes item
    from app.services.digest.builder import _candidates

    candidates = await _candidates(user_a, [source_a.id], [], datetime.now(UTC), db_session)
    assert not any(c.id == item.id for c in candidates)


@pytest.mark.asyncio
async def test_future_ingestion_blocks_url_and_host(db_session):
    """Future ingestion does not insert blocked items."""
    from app.services.discovery.pool import _store
    from app.workers.tasks.ingest_feeds import _insert_items

    # Block a specific URL and a whole host
    await add_blocked_entry(db_session, "https://blocked.example.com/story-1", "URL takedown")
    await add_blocked_entry(db_session, "spamsite.net", "Host takedown")
    await db_session.commit()

    rows = [
        {"url": "https://blocked.example.com/story-1", "title": "Blocked URL", "word_count": 10},
        {"url": "https://spamsite.net/article-2", "title": "Blocked Host", "word_count": 10},
        {"url": "https://goodsite.com/article-3", "title": "Good Article", "word_count": 10},
    ]

    new_ids = await _insert_items(db_session, rows)
    await db_session.commit()

    # Only good article is inserted
    assert len(new_ids) == 1
    item = await db_session.get(ContentItem, new_ids[0])
    assert item is not None
    assert item.url == "https://goodsite.com/article-3"
