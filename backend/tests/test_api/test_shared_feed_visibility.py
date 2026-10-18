"""A feed's items reach every user who follows it (#108).

Public items are stored once, under whichever subscriber's source ingested
them first. Every later subscriber must still see them, with their own trust,
and never see another user's private items.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.digest import DigestItem
from app.models.source import Source
from app.models.user import User
from app.services.digest.builder import build_digest
from app.services.ingestion.rss_parser import RawContentItem
from tests.conftest import TestingSessionLocal

FEED = "https://shared.example.com/feed"


async def _ingest(items: list[RawContentItem]) -> None:
    from app.workers.tasks import ingest_feeds

    async def dispatch(source, session):
        return list(items) if source.feed_url == FEED else []

    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.services.ingestion.dispatcher.dispatch_source", dispatch),
        patch("app.workers.tasks.compute_embeddings.compute_embedding_for_item.delay"),
    ):
        await ingest_feeds._ingest_all_feeds_async()


async def _two_subscribers(db_session) -> tuple[User, User, Source, Source]:
    a = User(
        email=f"a{uuid.uuid4().hex[:6]}@example.com", hashed_password="x", onboarding_complete=True
    )
    b = User(
        email=f"b{uuid.uuid4().hex[:6]}@example.com", hashed_password="x", onboarding_complete=True
    )
    db_session.add_all([a, b])
    await db_session.flush()
    src_a = Source(user_id=a.id, url="https://shared.example.com", feed_url=FEED, trust_weight=0.5)
    src_b = Source(user_id=b.id, url="https://shared.example.com", feed_url=FEED, trust_weight=0.5)
    db_session.add_all([src_a, src_b])
    await db_session.commit()
    return a, b, src_a, src_b


@pytest.mark.asyncio
async def test_second_subscriber_gets_shared_items_in_digest(db_session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "digest_per_source_cap", 20)
    a, b, _, _ = await _two_subscribers(db_session)
    await _ingest(
        [
            RawContentItem(url=f"https://shared.example.com/p{i}", title=f"Post {i}", guid=f"g{i}")
            for i in range(10)
        ]
    )

    async with TestingSessionLocal() as s:
        user_b = await s.get(User, b.id)
        digest = await build_digest(user_b, s)
        await s.commit()
        rows = (
            await s.execute(
                select(ContentItem.url, DigestItem.section)
                .join(DigestItem, DigestItem.content_item_id == ContentItem.id)
                .where(DigestItem.digest_id == digest.id)
            )
        ).all()
    shared = {
        url: section for url, section in rows if url.startswith("https://shared.example.com/p")
    }
    # Before #108 these reached B only through the serendipity pool, mislabeled
    # as "discovery" even though B follows the feed.
    assert len(shared) >= 4  # lead size; under-fill beyond lead is tracked separately
    assert all(section != "discovery" for section in shared.values()), shared


@pytest.mark.asyncio
async def test_other_users_private_items_on_the_same_feed_stay_hidden(db_session):
    a, b, src_a, _ = await _two_subscribers(db_session)
    db_session.add(
        ContentItem(
            source_id=src_a.id,
            owner_user_id=a.id,
            url="https://shared.example.com/private",
            title="A's private copy",
            fetched_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    user_b = await db_session.get(User, b.id)
    digest = await build_digest(user_b, db_session)
    ids = {
        row[0]
        for row in (
            await db_session.execute(
                select(DigestItem.content_item_id).where(DigestItem.digest_id == digest.id)
            )
        ).all()
    }
    private = (
        await db_session.execute(select(ContentItem.id).where(ContentItem.url.endswith("/private")))
    ).scalar_one()
    assert private not in ids


@pytest.mark.asyncio
async def test_reading_a_shared_item_moves_only_the_readers_trust(db_session):
    from app.services.interest_graph.updater import update_from_interaction

    a, b, src_a, src_b = await _two_subscribers(db_session)
    await _ingest(
        [RawContentItem(url="https://shared.example.com/read-me", title="Read me", guid="r1")]
    )
    item = (
        await db_session.execute(select(ContentItem).where(ContentItem.url.endswith("/read-me")))
    ).scalar_one()
    # Stored once, under one subscriber's row (both rows share a created_at
    # here, so which one is decided by id). The *other* subscriber reads it.
    assert item.source_id in (src_a.id, src_b.id)
    filer, reader_src = (src_a, src_b) if item.source_id == src_a.id else (src_b, src_a)
    reader = b if reader_src is src_b else a
    item.topic_clusters = ["airships"]

    interaction = UserContentInteraction(
        user_id=reader.id, content_item_id=item.id, read_completion_pct=0.95
    )
    db_session.add(interaction)
    await db_session.flush()
    await update_from_interaction(interaction, item, db_session)
    await db_session.commit()

    await db_session.refresh(filer)
    await db_session.refresh(reader_src)
    assert filer.trust_weight == pytest.approx(0.5)
    assert reader_src.trust_weight > 0.5


@pytest.mark.asyncio
async def test_trust_signal_reads_the_users_own_source(db_session):
    from app.services.ranking.ranker import rank

    a, b, src_a, src_b = await _two_subscribers(db_session)
    src_a.trust_weight, src_b.trust_weight = 0.9, 0.2
    item = ContentItem(source_id=src_a.id, url="https://shared.example.com/t", title="T")
    db_session.add(item)
    await db_session.commit()

    user_b = await db_session.get(User, b.id)
    scored = (await rank(user_b, [item], db_session))[0]
    assert scored.features["source_trust"] == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_items_per_week_and_search_cover_shared_items(client: AsyncClient, db_session):
    data = {"email": f"s{uuid.uuid4().hex[:6]}@example.com", "password": "TestPass123!"}
    reg = await client.post("/api/v1/auth/register", json=data)
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    viewer = (
        await db_session.execute(select(User).where(User.email == data["email"]))
    ).scalar_one()
    first = User(email=f"f{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    db_session.add(first)
    await db_session.flush()
    src_first = Source(user_id=first.id, url="https://shared.example.com", feed_url=FEED)
    db_session.add_all(
        [src_first, Source(user_id=viewer.id, url="https://shared.example.com", feed_url=FEED)]
    )
    await db_session.flush()
    db_session.add(
        ContentItem(
            source_id=src_first.id,
            url="https://shared.example.com/zeppelin",
            title="Zeppelin internals explained",
            fetched_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    listed = await client.get("/api/v1/sources", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["items_per_week"] == 1

    found = await client.get("/api/v1/search", params={"q": "zeppelin"}, headers=headers)
    assert found.status_code == 200
    assert any("zeppelin" in hit["url"] for hit in found.json()["hits"])
