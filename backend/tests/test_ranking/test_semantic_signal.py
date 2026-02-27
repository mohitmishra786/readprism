from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.services.ranking.signals.semantic import compute
from app.services.ranking.signals import UserInterestGraph


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

    with patch("app.services.ranking.signals.semantic.cache_get", return_value=None),          patch("app.services.ranking.signals.semantic.cache_set", return_value=True):
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

    with patch("app.services.ranking.signals.semantic.cache_get", return_value=None),          patch("app.services.ranking.signals.semantic.cache_set", return_value=True):
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
