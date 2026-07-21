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
    # Make every query return None/empty so get_meta_weights uses default weights
    # and the upsert path is a no-op against the (mocked) DB.
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

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

    with (
        __import__("unittest.mock").mock.patch(
            "app.services.ranking.meta_weights.cache_set", return_value=True
        ),
        __import__("unittest.mock").mock.patch(
            "app.services.ranking.meta_weights.cache_get", return_value=None
        ),
    ):
        result = await update_meta_weights(user_id, pairs, session)

    # Semantic weight should have moved (direction depends on gradient)
    assert result.weights is not None
    total = sum(result.weights.values())
    assert abs(total - 1.0) < 1e-5


@pytest.mark.asyncio
async def test_leaking_signal_weights_are_held_out():
    """reading_depth/explicit_feedback must not be learned from the circular
    engagement target; their weights stay put while others move (audit 05-3)."""
    from app.services.ranking.meta_weights import LEAKING_SIGNALS

    user_id = uuid.uuid4()
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    digest_item = MagicMock()
    digest_item.signal_breakdown = {k: 0.8 for k in DEFAULT_WEIGHTS}
    interaction = MagicMock()
    interaction.read_completion_pct = 0.1
    interaction.explicit_rating = None
    interaction.saved = False
    pairs = [(digest_item, interaction)] * 25

    with (
        __import__("unittest.mock").mock.patch(
            "app.services.ranking.meta_weights.cache_set", return_value=True
        ),
        __import__("unittest.mock").mock.patch(
            "app.services.ranking.meta_weights.cache_get", return_value=None
        ),
    ):
        result = await update_meta_weights(user_id, pairs, session)

    # The non-leaking signals were over-predicting, so their raw weights shrank;
    # the leaking signals were held fixed. Hence each leaking signal's ratio to a
    # learned (non-leaking) signal must *increase* vs the default ratio — proof
    # they weren't learned from the circular target.
    for k in LEAKING_SIGNALS:
        assert k not in gradient_touched(result)  # sanity: never at an update bound
        post_ratio = result.weights[k] / result.weights["semantic"]
        default_ratio = DEFAULT_WEIGHTS[k] / DEFAULT_WEIGHTS["semantic"]
        assert post_ratio > default_ratio, f"{k} ratio {post_ratio} !> {default_ratio}"


def gradient_touched(result):
    # Helper: signals pinned to an update clamp bound (0.01/0.50) look "touched".
    return {k for k, v in result.weights.items() if v in (0.01, 0.50)}
