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

    kept, perspectives = await _synthesize_topic_clusters([a, b], db_session)
    assert len(kept) == 1
    assert len(perspectives[kept[0].id]) == 1
    payload = perspectives[kept[0].id][0]
    assert payload["source_id"] == str(src_b.id)
    assert payload["title"] == "Story B"

    # DigestItem breakdown carries perspectives end-to-end (unit-level check
    # of the wiring contract): the field lives on signal_breakdown JSONB.
    di = DigestItem(
        digest_id=uuid.uuid4(),
        content_item_id=a.id,
        position=0,
        section="lead",
        prs_score=0.5,
        signal_breakdown={"perspectives": perspectives[a.id]},
    )
    assert di.signal_breakdown["perspectives"][0]["url"] == "https://sb.example/story"
