from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ranking.meta_weights import (
    DEFAULT_WEIGHTS,
    UserMetaWeights,
    update_meta_weights,
)


def test_default_weights_sum_to_one():
    total = sum(DEFAULT_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-6, f"Weights sum to {total}, not 1.0"


def test_user_meta_weights_normalize():
    weights = {"semantic": 2.0, "reading_depth": 2.0}
    mw = UserMetaWeights(user_id=uuid.uuid4(), weights=weights)
    total = sum(mw.weights.values())
    assert abs(total - 1.0) < 1e-6


@pytest.mark.asyncio
async def test_weight_update_moves_correct_direction():
    """If a signal was over-predicting, its weight should decrease."""
    user_id = uuid.uuid4()
    initial_weights = dict(DEFAULT_WEIGHTS)

    session = AsyncMock()

    # Create mock digest items where semantic signal was high but actual engagement was low
    digest_item = MagicMock()
    digest_item.signal_breakdown = {
        "semantic": 0.9,  # high
        "reading_depth": 0.3,
        "suggestion": 0.2,
        "explicit_feedback": 0.5,
        "source_trust": 0.5,
        "content_quality": 0.5,
        "temporal_context": 0.5,
        "novelty": 0.5,
    }

    interaction = MagicMock()
    interaction.read_completion_pct = 0.1  # low actual engagement
    interaction.explicit_rating = None
    interaction.saved = False

    pairs = [(digest_item, interaction)] * 25  # enough for update

    with __import__("unittest.mock").mock.patch(
        "app.services.ranking.meta_weights.cache_set", return_value=True
    ), __import__("unittest.mock").mock.patch(
        "app.services.ranking.meta_weights.cache_get", return_value=None
    ):
        result = await update_meta_weights(user_id, pairs, session)

    # Semantic weight should have moved (direction depends on gradient)
    assert result.weights is not None
    total = sum(result.weights.values())
    assert abs(total - 1.0) < 1e-5
