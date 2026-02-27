from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ranking.signals.temporal_context import (
    SATURATION_PENALTY_PER_ITEM,
    MAX_SATURATION_PENALTY,
    _short_term_adjustment,
)
from app.services.ranking.signals import UserInterestGraph


@pytest.mark.asyncio
async def test_saturation_penalty_with_5_similar_items():
    """After 5 similar items in 72h, saturation penalty is applied."""
    content = MagicMock()
    content.id = uuid.uuid4()
    content.embedding = [1.0] + [0.0] * 383

    user = MagicMock()
    user.id = uuid.uuid4()

    # 5 similar items above threshold similarity
    similar_embeddings = [[1.0] + [0.0] * 383 for _ in range(5)]

    session = AsyncMock()
    session.execute = AsyncMock()

    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(emb,) for emb in similar_embeddings]
    session.execute.return_value = mock_result

    adjustment = await _short_term_adjustment(content, user, session)

    expected_penalty = min(MAX_SATURATION_PENALTY, 5 * SATURATION_PENALTY_PER_ITEM)
    expected_adjustment = 1.0 - expected_penalty
    assert abs(adjustment - expected_adjustment) < 0.01,         f"Expected {expected_adjustment:.2f} but got {adjustment:.2f}"


@pytest.mark.asyncio
async def test_no_recent_items_no_penalty():
    """No similar items in 72h means no saturation penalty."""
    content = MagicMock()
    content.id = uuid.uuid4()
    content.embedding = [1.0] + [0.0] * 383

    user = MagicMock()
    user.id = uuid.uuid4()

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    session.execute.return_value = mock_result

    adjustment = await _short_term_adjustment(content, user, session)
    assert adjustment == 1.0
