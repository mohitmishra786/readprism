"""A brand-new user reaches a non-empty first digest (#102)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.models.content import ContentItem
from app.models.digest import Digest, DigestItem
from app.models.source import Source
from app.models.user import User
from app.services.cold_start import first_digest_flow
from app.services.ingestion.rss_parser import RawContentItem
from tests.conftest import TestingSessionLocal


def _vec(i: int) -> list[float]:
    v = [0.0] * 384
    v[i % 384] = 1.0
    return v


def _fake_dispatch(topics_per_feed: int = 3):
    async def dispatch(source, session):
        base = (source.feed_url or source.url).rstrip("/")
        return [
            RawContentItem(url=f"{base}/post-{i}", title=f"{base} post {i}", guid=f"{base}-{i}")
            for i in range(topics_per_feed)
        ]

    return dispatch


async def _register(client: AsyncClient) -> tuple[dict, uuid.UUID]:
    data = {"email": f"new{uuid.uuid4().hex[:6]}@example.com", "password": "TestPass123!"}
    reg = await client.post("/api/v1/auth/register", json=data)
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    async with TestingSessionLocal() as s:
        user_id = (await s.execute(select(User.id).where(User.email == data["email"]))).scalar_one()
    return headers, user_id


async def _simulate_embedding(user_id: uuid.UUID) -> None:
    """Stand-in for the embed worker: give every item an embedding and topics."""
    async with TestingSessionLocal() as s:
        items = list((await s.execute(select(ContentItem))).scalars())
        for i, item in enumerate(items):
            item.embedding = _vec(i)
            item.topic_clusters = [f"topic-{i % 4}"]
            item.summary_brief = f"Summary {i}"
        await s.commit()


@pytest.mark.asyncio
async def test_signup_with_two_packs_reaches_a_real_first_digest(client: AsyncClient, monkeypatch):
    from app.config import get_settings
    from app.services.cold_start.starter_packs import list_starter_packs
    from app.workers.tasks import build_digest as build_task
    from app.workers.tasks import ingest_feeds

    monkeypatch.setattr(get_settings(), "digest_per_source_cap", 3)
    headers, user_id = await _register(client)
    onboard = await client.post(
        "/api/v1/onboarding",
        json={
            "interest_text": "systems programming and databases",
            "sample_ratings": [],
            "source_opml": None,
        },
        headers=headers,
    )
    assert onboard.status_code == 200
    packs = list_starter_packs()[:2]
    for pack in packs:
        assert (
            await client.post(f"/api/v1/sources/starter-packs/{pack.id}/subscribe", headers=headers)
        ).status_code == 200

    store: set[str] = set()

    async def fake_nx(key, value, ttl_seconds):
        if key in store:
            return False
        store.add(key)
        return True

    with (
        patch("app.utils.cache.cache_set_nx", fake_nx),
        patch("app.workers.tasks.ingest_feeds.ingest_user_sources.delay") as ingest_delay,
        patch("app.workers.tasks.build_digest.prepare_first_digest.apply_async") as prepare_async,
    ):
        started = await client.post("/api/v1/onboarding/first-digest", headers=headers)
        again = await client.post("/api/v1/onboarding/first-digest", headers=headers)
    assert started.json()["started"] is True and again.json()["started"] is False
    ingest_delay.assert_called_once_with(str(user_id))
    prepare_async.assert_called_once()
    assert started.json()["digest_id"] is None

    # Worker side: fetch only this user's sources, embed, then prepare.
    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.services.ingestion.dispatcher.dispatch_source", _fake_dispatch()),
        patch("app.workers.tasks.compute_embeddings.compute_embedding_for_item.delay"),
    ):
        await ingest_feeds._ingest_all_feeds_async(user_id=user_id)
    await _simulate_embedding(user_id)

    status = (await client.get("/api/v1/onboarding/first-digest/status", headers=headers)).json()
    assert status["ready"] and status["sources_fetched"] == status["sources_total"] > 0

    deadline = datetime.now(UTC) + timedelta(minutes=3)
    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.utils.cache.cache_set_nx", fake_nx),
        patch("app.workers.tasks.deliver_digest.deliver_digest_task.delay"),
    ):
        result = await build_task._prepare_first_digest_async(user_id, deadline)
    assert result["status"] == "ok"

    async with TestingSessionLocal() as s:
        digest = (await s.execute(select(Digest).where(Digest.user_id == user_id))).scalar_one()
        rows = (
            await s.execute(
                select(ContentItem.topic_clusters)
                .join(DigestItem, DigestItem.content_item_id == ContentItem.id)
                .where(DigestItem.digest_id == digest.id)
            )
        ).all()
    topics = {t for (clusters,) in rows for t in (clusters or [])}
    assert len(rows) >= 5
    assert len(topics) >= 3


@pytest.mark.asyncio
async def test_prepare_waits_then_builds_at_the_deadline(db_session):
    from app.workers.tasks import build_digest as build_task

    user = User(email="slow@example.com", hashed_password="x", onboarding_complete=True)
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        Source(
            user_id=user.id, url="https://slow.example.com", feed_url="https://slow.example.com/f"
        )
    )
    await db_session.commit()

    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch.object(build_task.prepare_first_digest, "apply_async") as again,
    ):
        waiting = await build_task._prepare_first_digest_async(
            user.id, datetime.now(UTC) + timedelta(minutes=2)
        )
    assert waiting["status"] == "waiting"
    again.assert_called_once()

    async def any_lock(key, value, ttl_seconds):
        return True

    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.utils.cache.cache_set_nx", any_lock),
        patch("app.workers.tasks.deliver_digest.deliver_digest_task.delay"),
    ):
        built = await build_task._prepare_first_digest_async(
            user.id, datetime.now(UTC) - timedelta(seconds=1)
        )
    assert built["status"] == "ok"  # builds with whatever exists rather than never


@pytest.mark.asyncio
async def test_user_scoped_ingest_ignores_schedule_and_other_users(db_session):
    from app.workers.tasks import ingest_feeds

    me = User(email="me@example.com", hashed_password="x")
    other = User(email="other@example.com", hashed_password="x")
    db_session.add_all([me, other])
    await db_session.flush()
    future = datetime.now(UTC) + timedelta(hours=6)
    db_session.add_all(
        [
            Source(
                user_id=me.id,
                url="https://mine.example.com",
                feed_url="https://mine.example.com/f",
                next_poll_at=future,
            ),
            Source(
                user_id=other.id,
                url="https://theirs.example.com",
                feed_url="https://theirs.example.com/f",
            ),
        ]
    )
    await db_session.commit()

    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.services.ingestion.dispatcher.dispatch_source", _fake_dispatch(2)),
        patch("app.workers.tasks.compute_embeddings.compute_embedding_for_item.delay"),
    ):
        result = await ingest_feeds._ingest_all_feeds_async(user_id=me.id)

    async with TestingSessionLocal() as s:
        urls = {row[0] for row in (await s.execute(select(ContentItem.url))).all()}
    assert result["sources_processed"] == 1
    assert urls == {"https://mine.example.com/f/post-0", "https://mine.example.com/f/post-1"}


def test_readiness_rule():
    assert not first_digest_flow.is_ready(4, 4)
    assert not first_digest_flow.is_ready(10, 3)
    assert first_digest_flow.is_ready(10, 4)
    assert first_digest_flow.is_ready(5, 5)


@pytest.mark.asyncio
async def test_status_ignores_other_users_private_items(db_session):
    me = User(email="status-me@example.com", hashed_password="x")
    other = User(email="status-other@example.com", hashed_password="x")
    db_session.add_all([me, other])
    await db_session.flush()
    feed = "https://shared-status.example.com/f"
    mine = Source(user_id=me.id, url="https://shared-status.example.com", feed_url=feed)
    theirs = Source(user_id=other.id, url="https://shared-status.example.com", feed_url=feed)
    db_session.add_all([mine, theirs])
    await db_session.flush()
    for i in range(6):
        db_session.add(
            ContentItem(
                source_id=theirs.id, owner_user_id=other.id, url=f"{feed}/p{i}", title=f"P{i}"
            )
        )
    await db_session.commit()
    await db_session.execute(update(ContentItem).values(fetched_at=datetime.now(UTC)))
    await db_session.commit()

    status = await first_digest_flow.first_digest_status(db_session, me.id)
    assert status["items"] == 0
