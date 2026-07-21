from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.cold_start import collaborative
from app.services.cold_start.collaborative import get_collaborative_warmup_items


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


def _count_result(value: int) -> MagicMock:
    r = MagicMock()
    r.scalar.return_value = value
    return r


@pytest.fixture(autouse=True)
def _low_warmup_threshold(monkeypatch):
    # Most tests exercise the recommendation logic, so keep the active-user gate
    # satisfied (threshold 1) unless a test overrides it.
    monkeypatch.setattr(collaborative.settings, "collaborative_warmup_min_users", 1)
    monkeypatch.setattr(collaborative.settings, "cold_start_collaborative_enabled", True)


@pytest.mark.asyncio
async def test_gated_off_below_min_active_users(monkeypatch):
    """Below the active-user threshold, warmup is inert and returns []."""
    monkeypatch.setattr(collaborative.settings, "collaborative_warmup_min_users", 1000)
    user = _make_user()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_count_result(5))  # 5 < 1000
    result = await get_collaborative_warmup_items(user, limit=10, session=session)
    assert result == []


@pytest.mark.asyncio
async def test_returns_empty_when_no_interest_vector():
    user = _make_user()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_count_result(50))  # passes gate

    with patch(
        "app.services.cold_start.collaborative.graph_manager.build_user_interest_vector",
        return_value=None,
    ):
        result = await get_collaborative_warmup_items(user, limit=10, session=session)

    assert result == []


@pytest.mark.asyncio
async def test_returns_empty_when_no_candidate_users():
    import numpy as np

    user = _make_user()
    session = AsyncMock()
    user_vec = np.ones(384, dtype=np.float32) / 384**0.5

    no_candidates = MagicMock()
    no_candidates.fetchall.return_value = []
    session.execute = AsyncMock(side_effect=[_count_result(50), no_candidates])

    with patch(
        "app.services.cold_start.collaborative.graph_manager.build_user_interest_vector",
        return_value=user_vec,
    ):
        result = await get_collaborative_warmup_items(user, limit=10, session=session)

    assert result == []


@pytest.mark.asyncio
async def test_returns_empty_when_no_cache_hits():
    import numpy as np

    user = _make_user()
    session = AsyncMock()
    user_vec = np.ones(384, dtype=np.float32) / 384**0.5

    candidates = MagicMock()
    candidates.fetchall.return_value = [(str(uuid.uuid4()),)]
    session.execute = AsyncMock(side_effect=[_count_result(50), candidates])

    with (
        patch(
            "app.services.cold_start.collaborative.graph_manager.build_user_interest_vector",
            return_value=user_vec,
        ),
        patch("app.services.cold_start.collaborative.cache_get", return_value=None),
    ):
        result = await get_collaborative_warmup_items(user, limit=10, session=session)

    assert result == []


@pytest.mark.asyncio
async def test_returns_items_from_similar_users_recommendation_path():
    import numpy as np

    user = _make_user()
    user_vec = np.ones(384, dtype=np.float32) / (384**0.5)
    neighbor_id = uuid.uuid4()
    recommended_item = MagicMock()
    recommended_item.id = uuid.uuid4()

    session = AsyncMock()
    candidates_result = MagicMock()
    candidates_result.fetchall.return_value = [(neighbor_id,)]
    engagement_result = MagicMock()
    engagement_result.fetchall.return_value = [(recommended_item.id, 1)]
    load_result = MagicMock()
    load_result.scalars.return_value.all.return_value = [recommended_item]

    session.execute = AsyncMock(
        side_effect=[_count_result(50), candidates_result, engagement_result, load_result]
    )

    async def fake_cache_get(key):
        if str(neighbor_id) in key:
            return user_vec.tolist()
        return None

    with (
        patch(
            "app.services.cold_start.collaborative.graph_manager.build_user_interest_vector",
            return_value=user_vec,
        ),
        patch("app.services.cold_start.collaborative.cache_get", side_effect=fake_cache_get),
    ):
        result = await get_collaborative_warmup_items(user, limit=10, session=session)

    assert result == [recommended_item]
