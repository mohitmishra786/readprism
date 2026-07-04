"""Tests for the previously-untested ranking signals.

These mirror the convention in test_semantic_signal.py: construct MagicMock
content/user objects with controlled attributes, patch cache/network surfaces,
and assert the score lands where the math should put it.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ranking.signals import UserInterestGraph


# ---------------------------------------------------------------------------
# content_quality — pure deterministic function of content attributes.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_content_quality_high_quality_article():
    """A long, cited, original, in-depth article scores high."""
    from app.services.ranking.signals.content_quality import _compute_quality

    content = MagicMock()
    content.reading_time_minutes = 15
    content.word_count = 2500
    content.has_citations = True
    content.is_original_reporting = True
    content.content_depth_score = 0.9

    score = _compute_quality(content)
    assert score > 0.8, f"Expected high quality score, got {score}"


@pytest.mark.asyncio
async def test_content_quality_low_quality_article():
    """A short, uncited, non-original piece scores low."""
    from app.services.ranking.signals.content_quality import _compute_quality

    content = MagicMock()
    content.reading_time_minutes = 1
    content.word_count = 100
    content.has_citations = False
    content.is_original_reporting = False
    content.content_depth_score = 0.1

    score = _compute_quality(content)
    assert score < 0.4, f"Expected low quality score, got {score}"


@pytest.mark.asyncio
async def test_content_quality_caches_and_returns_cached():
    """compute() should cache the score and return the cached value on the second call."""
    from app.services.ranking.signals import content_quality as cq

    content = MagicMock()
    content.id = uuid.uuid4()
    content.reading_time_minutes = 10
    content.word_count = 1500
    content.has_citations = True
    content.is_original_reporting = True
    content.content_depth_score = 0.8

    cached_values: dict[str, float] = {}

    async def fake_get(key):
        return cached_values.get(key)

    async def fake_set(key, value, ttl_seconds=None):
        cached_values[key] = value

    user = MagicMock()
    graph = UserInterestGraph(nodes=[], edges=[])
    session = AsyncMock()

    with patch(
        "app.services.ranking.signals.content_quality.cache_get", side_effect=fake_get
    ), patch("app.services.ranking.signals.content_quality.cache_set", side_effect=fake_set):
        first = await cq.compute(content, user, [], graph, session)
        second = await cq.compute(content, user, [], graph, session)

    assert first == second
    assert f"quality:{content.id}" in cached_values


# ---------------------------------------------------------------------------
# source_trust — returns the learned Source.trust_weight, 0.4 fallback.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_source_trust_returns_learned_weight():
    """When the source exists, the signal returns its learned trust_weight."""
    from app.services.ranking.signals import source_trust

    content = MagicMock()
    content.source_id = uuid.uuid4()

    source = MagicMock()
    source.trust_weight = 0.82

    session = AsyncMock()
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = source
    session.execute = AsyncMock(return_value=scalar_result)

    user = MagicMock()
    graph = UserInterestGraph(nodes=[], edges=[])

    score = await source_trust.compute(content, user, [], graph, session)
    assert score == pytest.approx(0.82)


@pytest.mark.asyncio
async def test_source_trust_no_source_returns_neutral():
    """Content with no source_id returns the 0.4 fallback."""
    from app.services.ranking.signals import source_trust

    content = MagicMock()
    content.source_id = None

    session = AsyncMock()
    user = MagicMock()
    graph = UserInterestGraph(nodes=[], edges=[])

    score = await source_trust.compute(content, user, [], graph, session)
    assert score == 0.4


@pytest.mark.asyncio
async def test_source_trust_missing_source_returns_neutral():
    """Content with a source_id that doesn't resolve returns 0.4."""
    from app.services.ranking.signals import source_trust

    content = MagicMock()
    content.source_id = uuid.uuid4()

    session = AsyncMock()
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=scalar_result)

    user = MagicMock()
    graph = UserInterestGraph(nodes=[], edges=[])

    score = await source_trust.compute(content, user, [], graph, session)
    assert score == 0.4


# ---------------------------------------------------------------------------
# explicit_feedback — boosts similarity to positively-rated, penalizes negative.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_explicit_feedback_no_ratings_returns_neutral():
    """With no explicit ratings, the signal returns 0.5."""
    from app.services.ranking.signals import explicit_feedback

    content = MagicMock()
    content.embedding = [0.1] * 384
    user = MagicMock()
    graph = UserInterestGraph(nodes=[], edges=[])
    session = AsyncMock()

    score = await explicit_feedback.compute(content, user, [], graph, session)
    assert score == 0.5


@pytest.mark.asyncio
async def test_explicit_feedback_no_embedding_returns_neutral():
    """Without a content embedding, similarity can't be computed → 0.5."""
    from app.services.ranking.signals import explicit_feedback

    content = MagicMock()
    content.embedding = None
    user = MagicMock()

    rated = MagicMock()
    rated.explicit_rating = 1
    rated.content_item_id = uuid.uuid4()

    graph = UserInterestGraph(nodes=[], edges=[])
    session = AsyncMock()

    score = await explicit_feedback.compute(content, user, [rated], graph, session)
    assert score == 0.5


# ---------------------------------------------------------------------------
# suggestion — neutral for new users (< 14 days), neutral without embedding.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_suggestion_signal_new_user_returns_neutral():
    """Users younger than 14 days get a neutral suggestion score."""
    from app.services.ranking.signals import suggestion

    content = MagicMock()
    content.embedding = [0.1] * 384

    user = MagicMock()
    user.created_at = datetime.now(UTC) - timedelta(days=2)

    graph = UserInterestGraph(nodes=[], edges=[])
    session = AsyncMock()

    score = await suggestion.compute(content, user, [], graph, session)
    assert score == 0.5


@pytest.mark.asyncio
async def test_suggestion_signal_no_embedding_returns_neutral():
    """Content without an embedding returns neutral."""
    from app.services.ranking.signals import suggestion

    content = MagicMock()
    content.embedding = None

    user = MagicMock()
    user.created_at = datetime.now(UTC) - timedelta(days=30)

    graph = UserInterestGraph(nodes=[], edges=[])
    session = AsyncMock()

    score = await suggestion.compute(content, user, [], graph, session)
    assert score == 0.5


# ---------------------------------------------------------------------------
# novelty — neutral without embedding; peaks at TARGET_NOVELTY similarity.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_novelty_no_embedding_returns_neutral():
    """Content without an embedding returns 0.5."""
    from app.services.ranking.signals import novelty

    content = MagicMock()
    content.id = uuid.uuid4()
    content.embedding = None

    user = MagicMock()
    user.id = uuid.uuid4()
    graph = UserInterestGraph(nodes=[], edges=[])
    session = AsyncMock()

    score = await novelty.compute(content, user, [], graph, session)
    assert score == 0.5


@pytest.mark.asyncio
async def test_novelty_empty_history_returns_neutral():
    """With an embedding but no read history, the signal returns 0.5."""
    from app.services.ranking.signals import novelty

    content = MagicMock()
    content.id = uuid.uuid4()
    content.embedding = [0.1] * 384

    user = MagicMock()
    user.id = uuid.uuid4()
    graph = UserInterestGraph(nodes=[], edges=[])

    session = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = []
    session.execute = AsyncMock(return_value=result)

    score = await novelty.compute(content, user, [], graph, session)
    assert score == 0.5
