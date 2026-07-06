from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.cold_start.collaborative import get_collaborative_warmup_items


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


@pytest.mark.asyncio
async def test_returns_empty_when_no_interest_vector():
    """If the user has no interest vector, collaborative warmup returns empty list."""
    user = _make_user()
    session = AsyncMock()

    with patch(
        "app.services.cold_start.collaborative.graph_manager.build_user_interest_vector",
        return_value=None,
    ):
        result = await get_collaborative_warmup_items(user, limit=10, session=session)

    assert result == []


@pytest.mark.asyncio
async def test_returns_empty_when_no_candidate_users():
    """If there are no candidate users in the DB, return empty list."""
    import numpy as np

    user = _make_user()
    session = AsyncMock()
    user_vec = np.ones(384, dtype=np.float32) / 384**0.5

    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    with patch(
        "app.services.cold_start.collaborative.graph_manager.build_user_interest_vector",
        return_value=user_vec,
    ):
        result = await get_collaborative_warmup_items(user, limit=10, session=session)

    assert result == []


@pytest.mark.asyncio
async def test_returns_empty_when_no_cache_hits():
    """If similar users have no cached interest vectors, return empty list."""
    import numpy as np

    user = _make_user()
    session = AsyncMock()
    user_vec = np.ones(384, dtype=np.float32) / 384**0.5

    mock_candidates_result = MagicMock()
    mock_candidates_result.fetchall.return_value = [(str(uuid.uuid4()),)]
    session.execute = AsyncMock(return_value=mock_candidates_result)

    with (
        patch(
            "app.services.cold_start.collaborative.graph_manager.build_user_interest_vector",
            return_value=user_vec,
        ),
        patch(
            "app.services.cold_start.collaborative.cache_get",
            return_value=None,  # No cached vectors
        ),
    ):
        result = await get_collaborative_warmup_items(user, limit=10, session=session)

    assert result == []


@pytest.mark.asyncio
async def test_returns_items_from_similar_users_recommendation_path():
    """The actual recommendation path: similar users' positively-rated items are returned.

    This is the gap flagged in the audit — the existing tests only covered empty
    edge cases, not the happy path through the similarity + engagement query.
    """
    import numpy as np

    user = _make_user()
    user_vec = np.ones(384, dtype=np.float32) / (384**0.5)

    # A neighbor user whose cached interest vector is identical → max similarity.
    neighbor_id = uuid.uuid4()

    recommended_item = MagicMock()
    recommended_item.id = uuid.uuid4()

    session = AsyncMock()

    # First execute() → candidate users; second → engagement query returning one row;
    # third → load ContentItem by id.
    candidates_result = MagicMock()
    candidates_result.fetchall.return_value = [(neighbor_id,)]

    engagement_result = MagicMock()
    # The engagement row's first column is the content id (used to load the item).
    engagement_result.fetchall.return_value = [(recommended_item.id, 1)]

    load_result = MagicMock()
    load_result.scalars.return_value.all.return_value = [recommended_item]

    session.execute = AsyncMock(side_effect=[candidates_result, engagement_result, load_result])

    async def fake_cache_get(key):
        # Return a cached interest vector for the neighbor only.
        if str(neighbor_id) in key:
            return user_vec.tolist()
        return None

    with (
        patch(
            "app.services.cold_start.collaborative.graph_manager.build_user_interest_vector",
            return_value=user_vec,
        ),
        patch(
            "app.services.cold_start.collaborative.cache_get",
            side_effect=fake_cache_get,
        ),
    ):
        result = await get_collaborative_warmup_items(user, limit=10, session=session)

    assert result == [recommended_item]
