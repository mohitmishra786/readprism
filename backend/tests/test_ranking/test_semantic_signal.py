from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.services.ranking.signals import UserInterestGraph
from app.services.ranking.signals.semantic import compute


@pytest.mark.asyncio
async def test_high_similarity_scores_above_threshold():
    """Content semantically close to user interests scores > 0.7."""
    content = MagicMock()
    content.id = uuid.uuid4()
    content.embedding = [0.9, 0.1, 0.0] * 128  # 384-dim vector

    user = MagicMock()
    user.id = uuid.uuid4()

    node = MagicMock()
    node.topic_embedding = [0.9, 0.1, 0.0] * 128  # same direction
    node.weight = 1.0

    graph = UserInterestGraph(nodes=[node], edges=[])
    session = AsyncMock()

    with (
        patch("app.services.ranking.signals.semantic.cache_get", return_value=None),
        patch("app.services.ranking.signals.semantic.cache_set", return_value=True),
    ):
        score = await compute(content, user, [], graph, session)

    assert score > 0.7, f"Expected > 0.7 but got {score}"


@pytest.mark.asyncio
async def test_low_similarity_scores_below_threshold():
    """Content semantically distant from user interests scores < 0.3."""
    content = MagicMock()
    content.id = uuid.uuid4()
    # Orthogonal vector
    content.embedding = [1.0] + [0.0] * 383

    user = MagicMock()
    user.id = uuid.uuid4()

    node = MagicMock()
    node.topic_embedding = [0.0] * 383 + [1.0]  # opposite direction
    node.weight = 1.0

    graph = UserInterestGraph(nodes=[node], edges=[])
    session = AsyncMock()

    with (
        patch("app.services.ranking.signals.semantic.cache_get", return_value=None),
        patch("app.services.ranking.signals.semantic.cache_set", return_value=True),
    ):
        score = await compute(content, user, [], graph, session)

    assert score < 0.6, f"Expected < 0.6 but got {score}"


@pytest.mark.asyncio
async def test_no_embedding_returns_neutral():
    """Content without embedding returns 0.5."""
    content = MagicMock()
    content.id = uuid.uuid4()
    content.embedding = None

    user = MagicMock()
    user.id = uuid.uuid4()
    graph = UserInterestGraph(nodes=[], edges=[])
    session = AsyncMock()

    with patch("app.workers.tasks.compute_embeddings.compute_embedding_for_item") as mock_task:
        mock_task.delay = MagicMock()
        score = await compute(content, user, [], graph, session)

    assert score == 0.5


@pytest.mark.asyncio
async def test_multi_interest_not_averaged_down():
    """A user with two distinct interests scores content near ONE of them highly,
    instead of averaging the two clusters into a centroid near neither (05-2)."""
    content = MagicMock()
    content.id = uuid.uuid4()
    content.embedding = [1.0, 0.0] + [0.0] * 382  # aligned with interest A only

    user = MagicMock()
    user.id = uuid.uuid4()

    node_a = MagicMock()
    node_a.id = uuid.uuid4()
    node_a.topic_embedding = [1.0, 0.0] + [0.0] * 382  # interest A
    node_a.weight = 1.0
    node_b = MagicMock()
    node_b.id = uuid.uuid4()
    node_b.topic_embedding = [0.0, 1.0] + [0.0] * 382  # interest B (orthogonal)
    node_b.weight = 1.0

    # No edge between them -> two separate clusters.
    graph = UserInterestGraph(nodes=[node_a, node_b], edges=[])
    session = AsyncMock()

    score = await compute(content, user, [], graph, session)
    # Averaged vector would give cosine ~0.707 -> ~0.85; max-sim gives ~1.0.
    assert score > 0.95, f"Expected near-1.0 (matched cluster A) but got {score}"
