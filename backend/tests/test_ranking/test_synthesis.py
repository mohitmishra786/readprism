"""Cross-source story synthesis (UX-09)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.content import ContentItem
from app.models.digest import DigestItem
from app.models.source import Source
from app.models.user import User
from app.services.digest.synthesis import cluster_stories, title_overlap


def test_embedding_pairs_cluster_and_title_overlap_fallback():
    items = [
        type("I", (), {"title": "", "embedding": [1.0, 0.0, 0.0, 0.0]}),
        type("I", (), {"title": "", "embedding": [0.99, 0.05, 0.0, 0.0]}),
        # No embeddings: title overlap decides.
        type("I", (), {"title": "Rust async runtime rewrite", "embedding": None}),
        type("I", (), {"title": "Rust async runtime rewrite explained", "embedding": None}),
        type("I", (), {"title": "Baking sourdough at home", "embedding": None}),
    ]
    clusters = cluster_stories(items)
    assert len(clusters) == 3  # (0,1), (2,3), (4)


def test_title_overlap_thresholds():
    assert title_overlap("Rust async runtime rewrite", "Rust async runtime rewrite") == 1.0
    assert title_overlap("Rust async runtime rewrite", "Sourdough starter guide") == 0.0


def test_title_path_requires_both_vectors_missing():
    """One vector present means no comparison happened — never cluster."""
    items = [
        type("I", (), {"title": "Rust async runtime rewrite", "embedding": [1.0, 0.0, 0.0, 0.0]}),
        type("I", (), {"title": "Rust async runtime rewrite", "embedding": None}),
    ]
    assert cluster_stories(items) == [[0], [1]]


def test_title_path_requires_enough_tokens():
    """Short titles ("Apple earnings") cannot claim a story match."""
    items = [
        type("I", (), {"title": "Apple earnings", "embedding": None}),
        type("I", (), {"title": "Apple earnings call", "embedding": None}),
    ]
    assert cluster_stories(items) == [[0], [1]]


def _db_item(source_id, url, title, *, embedding=None):
    return ContentItem(
        source_id=source_id,
        url=url,
        title=title,
        fetched_at=datetime.now(UTC),
        embedding=embedding,
    )


@pytest.mark.asyncio
async def test_builder_attaches_perspectives(db_session):
    """A same-story pair becomes one card carrying the other source."""
    from unittest.mock import patch

    from app.services.digest.builder import _synthesize_topic_clusters

    user = User(email="synth@example.com", hashed_password="x")
    other = User(email="synth-other@example.com", hashed_password="x")
    db_session.add_all([user, other])
    await db_session.flush()
    src_a = Source(user_id=user.id, url="https://sa.example/feed")
    src_b = Source(user_id=other.id, url="https://sb.example/feed")
    db_session.add_all([src_a, src_b])
    await db_session.flush()

    vec = [1.0] + [0.0] * 383
    a = _db_item(src_a.id, "https://sa.example/story", "Story A", embedding=vec)
    b = _db_item(src_b.id, "https://sb.example/story", "Story B", embedding=[0.99] + [0.0] * 383)
    db_session.add_all([a, b])
    await db_session.commit()

    async def _no_cache(*args, **kwargs):
        return None

    with (
        patch("app.utils.cache.cache_get", _no_cache),
        patch(
            "app.services.summarization.groq_client.GroqSummarizer.synthesize_topic",
            return_value="",
        ),
    ):
        kept, story_payloads = await _synthesize_topic_clusters([a, b], db_session)
    assert len(kept) == 1
    payload = story_payloads[kept[0].id]
    assert len(payload["perspectives"]) == 1
    perspective = payload["perspectives"][0]
    assert perspective["source_id"] == str(src_b.id)
    assert perspective["title"] == "Story B"

    # The shared content row's own summary is never overwritten (CodeRabbit):
    # the briefing lives in the per-digest payload, not on the item.
    assert payload["story_briefing"] is None
    assert a.summary_brief is None
