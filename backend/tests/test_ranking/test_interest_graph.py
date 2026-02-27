from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.interest_graph.graph import (
    CORE_REINFORCEMENT_THRESHOLD,
    CORE_WEIGHT_THRESHOLD,
    InterestGraphManager,
)


def _make_node(weight: float = 0.5, reinforcement_count: int = 0, is_core: bool = False) -> MagicMock:
    node = MagicMock()
    node.weight = weight
    node.reinforcement_count = reinforcement_count
    node.is_core = is_core
    node.last_reinforced_at = None
    node.user_id = uuid.uuid4()
    return node


@pytest.mark.asyncio
async def test_reinforce_node_increases_weight():
    """Positive signal should increase node weight."""
    manager = InterestGraphManager()
    node = _make_node(weight=0.5, reinforcement_count=0)
    session = AsyncMock()

    with patch("app.services.interest_graph.graph.cache_delete", return_value=None):
        await manager.reinforce_node(node, signal_strength=1.0, session=session)

    assert node.weight > 0.5


@pytest.mark.asyncio
async def test_reinforce_node_decreases_weight_on_negative_signal():
    """Negative signal should decrease node weight."""
    manager = InterestGraphManager()
    node = _make_node(weight=0.5, reinforcement_count=0)
    session = AsyncMock()

    with patch("app.services.interest_graph.graph.cache_delete", return_value=None):
        await manager.reinforce_node(node, signal_strength=-0.8, session=session)

    assert node.weight < 0.5


@pytest.mark.asyncio
async def test_node_becomes_core_after_threshold():
    """Node should become core after enough high-weight reinforcements."""
    manager = InterestGraphManager()
    node = _make_node(
        weight=CORE_WEIGHT_THRESHOLD + 0.05,
        reinforcement_count=CORE_REINFORCEMENT_THRESHOLD - 1,
        is_core=False,
    )
    session = AsyncMock()

    with patch("app.services.interest_graph.graph.cache_delete", return_value=None):
        await manager.reinforce_node(node, signal_strength=0.5, session=session)

    assert node.is_core, "Node should be promoted to core after threshold"


@pytest.mark.asyncio
async def test_edge_weight_normalized():
    """Edge weight should be normalized to [0, 1] relative to max co-occurrence."""
    manager = InterestGraphManager()
    user_id = uuid.uuid4()
    a_id = uuid.uuid4()
    b_id = uuid.uuid4()

    edge = MagicMock()
    edge.co_occurrence_count = 0
    edge.edge_weight = 0.0

    session = AsyncMock()
    # First execute call: get existing edge (None → create new)
    # Second execute call: get max co_occurrence_count
    mock_none_result = MagicMock()
    mock_none_result.scalar_one_or_none.return_value = None

    mock_max_result = MagicMock()
    mock_max_result.scalar.return_value = 5  # max count is 5

    session.execute = AsyncMock(side_effect=[mock_none_result, mock_max_result])
    session.add = MagicMock()

    # Patch flush so the new edge object is available
    async def fake_flush():
        pass
    session.flush = fake_flush

    # We need to capture what gets added
    added_edge = None
    def capture_add(obj):
        nonlocal added_edge
        if hasattr(obj, "co_occurrence_count"):
            added_edge = obj
    session.add.side_effect = capture_add

    # Since the edge is created inside the function and we mock session.add,
    # we test the normalization logic separately here
    # Test the math: count=1, max=5 → weight=0.2
    test_edge = MagicMock()
    test_edge.co_occurrence_count = 4  # simulate an existing edge
    test_edge.edge_weight = 0.0

    mock_existing_result = MagicMock()
    mock_existing_result.scalar_one_or_none.return_value = test_edge
    mock_max_result2 = MagicMock()
    mock_max_result2.scalar.return_value = 10

    session.execute = AsyncMock(side_effect=[mock_existing_result, mock_max_result2])

    with patch("app.services.interest_graph.graph.cache_delete", return_value=None):
        await manager.reinforce_edge(user_id, a_id, b_id, session)

    # co_occurrence_count was 4, incremented to 5, max is 10 → weight = 5/10 = 0.5
    assert abs(test_edge.edge_weight - 0.5) < 1e-6
