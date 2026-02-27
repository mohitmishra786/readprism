from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ranking.scorer import compute_prs


@pytest.mark.asyncio
async def test_scorer_returns_score_between_0_and_1():
    """PRS must always be in [0, 1]."""
    content = MagicMock()
    content.id = uuid.uuid4()
    content.embedding = [0.5] * 384
    content.source_id = uuid.uuid4()
    content.creator_platform_id = None
    content.reading_time_minutes = 8
    content.word_count = 1000
    content.has_citations = True
    content.is_original_reporting = True
    content.content_depth_score = 0.7
    content.topic_clusters = ["machine learning"]

    user = MagicMock()
    user.id = uuid.uuid4()
    user.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

    session = AsyncMock()
    session.execute = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    with patch("app.services.ranking.meta_weights.cache_get", return_value=None),          patch("app.services.ranking.meta_weights.cache_set", return_value=True),          patch("app.services.ranking.signals.semantic.cache_get", return_value=None),          patch("app.services.ranking.signals.semantic.cache_set", return_value=True),          patch("app.services.ranking.signals.content_quality.cache_get", return_value=None),          patch("app.services.ranking.signals.content_quality.cache_set", return_value=True):
        prs, breakdown = await compute_prs(content, user, session)

    assert 0.0 <= prs <= 1.0, f"PRS {prs} out of range [0,1]"
    assert isinstance(breakdown, dict)
    assert len(breakdown) == 8
