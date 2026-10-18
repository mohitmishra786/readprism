"""LLM summaries only for items someone sees (#147)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.content import ContentItem
from app.models.source import Source
from app.models.user import User
from app.services.summarization.extractive import keyword_topics
from app.services.summarization.groq_client import SummarizationResult
from tests.conftest import TestingSessionLocal

BODY = (
    "Postgres vacuum keeps tables healthy. Autovacuum tuning matters for large tables. "
    "This post explains postgres vacuum internals, autovacuum thresholds and how dead tuples pile up. "
) * 5


def _llm_result(topic: str = "databases") -> SummarizationResult:
    return SummarizationResult(
        headline="LLM headline",
        brief="LLM brief.",
        detailed="LLM detailed.",
        depth_score=0.8,
        is_original_reporting=True,
        has_citations=True,
        topic_clusters=[topic],
        reading_time_minutes=6,
        summary_source="llm",
    )


@pytest.fixture
def llm_on(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_api_key", "test-key")
    fake = AsyncMock(return_value=_llm_result())
    with patch("app.services.summarization.groq_client.GroqSummarizer.summarize", fake):
        yield fake


def test_keyword_topics_without_an_llm():
    topics = keyword_topics("Postgres vacuum explained", BODY)
    assert topics and topics[0] == "postgres vacuum"
    assert len(topics) <= 3
    assert keyword_topics("", "") == []


@pytest.mark.asyncio
async def test_lazy_ingest_makes_no_llm_calls_but_still_has_topics(db_session, llm_on):
    from app.workers.tasks.compute_embeddings import _compute_embedding_async

    item = ContentItem(
        url=f"https://lz.example/{uuid.uuid4().hex}",
        title="Postgres vacuum explained",
        full_text=BODY,
    )
    db_session.add(item)
    await db_session.commit()

    with patch("app.database.AsyncSessionLocal", TestingSessionLocal):
        await _compute_embedding_async(item.id)

    async with TestingSessionLocal() as s:
        stored = await s.get(ContentItem, item.id)
    assert llm_on.await_count == 0
    assert stored.summary_source == "extractive"
    assert stored.topic_clusters and "postgres" in stored.topic_clusters[0]


@pytest.mark.asyncio
async def test_all_mode_still_summarizes_every_item(db_session, llm_on, monkeypatch):
    from app.config import get_settings
    from app.workers.tasks.compute_embeddings import _compute_embedding_async

    monkeypatch.setattr(get_settings(), "llm_summarize", "all")
    item = ContentItem(url=f"https://lz.example/{uuid.uuid4().hex}", title="T", full_text=BODY)
    db_session.add(item)
    await db_session.commit()

    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.utils.cache.cache_get", AsyncMock(return_value=None)),
    ):
        await _compute_embedding_async(item.id)
    assert llm_on.await_count == 1


@pytest.mark.asyncio
async def test_digest_asks_the_llm_only_for_placed_items(db_session, llm_on, monkeypatch):
    from app.config import get_settings
    from app.services.digest.builder import build_digest

    monkeypatch.setattr(get_settings(), "digest_per_source_cap", 50)
    user = User(
        email=f"lz{uuid.uuid4().hex[:6]}@example.com", hashed_password="x", digest_max_items=5
    )
    db_session.add(user)
    await db_session.flush()
    src = Source(user_id=user.id, url="https://lz.example", feed_url="https://lz.example/f")
    db_session.add(src)
    await db_session.flush()
    for i in range(30):
        db_session.add(
            ContentItem(
                source_id=src.id,
                url=f"https://lz.example/{i}",
                title=f"Item {i}",
                full_text=BODY,
                summary_source="extractive",
                fetched_at=datetime.now(UTC),
                topic_clusters=[f"t{i}"],
            )
        )
    await db_session.commit()

    digest = await build_digest(user, db_session)
    await db_session.commit()

    assert llm_on.await_count == digest.total_items <= 5  # 5 of 30 candidates
    summarized = (
        await db_session.execute(select(ContentItem.id).where(ContentItem.summary_source == "llm"))
    ).all()
    assert len(summarized) == digest.total_items


@pytest.mark.asyncio
async def test_opening_an_item_queues_one_llm_summary(client, db_session, llm_on):
    data = {"email": f"lo{uuid.uuid4().hex[:6]}@example.com", "password": "TestPass123!"}
    reg = await client.post("/api/v1/auth/register", json=data)
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    item = ContentItem(
        url=f"https://lz.example/{uuid.uuid4().hex}",
        title="T",
        full_text=BODY,
        summary_source="extractive",
    )
    db_session.add(item)
    await db_session.commit()

    store: set[str] = set()

    async def nx(key, value, ttl_seconds):
        if key in store:
            return False
        store.add(key)
        return True

    with (
        patch("app.utils.cache.cache_set_nx", nx),
        patch("app.workers.tasks.compute_embeddings.summarize_item_with_llm.delay") as delay,
    ):
        for _ in range(3):
            assert (
                await client.get(f"/api/v1/content/{item.id}", headers=headers)
            ).status_code == 200
    delay.assert_called_once_with(str(item.id))
