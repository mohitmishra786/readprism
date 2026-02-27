from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.interest_graph.decay import INACTIVE_WEIGHT_THRESHOLD, apply_decay


def _make_node(
    weight: float = 0.8,
    is_core: bool = False,
    half_life_days: int = 60,
    days_since_reinforced: float = 30.0,
    suppressed_until: datetime | None = None,
) -> MagicMock:
    node = MagicMock()
    node.weight = weight
    node.is_core = is_core
    node.half_life_days = half_life_days
    node.suppressed_until = suppressed_until
    if days_since_reinforced is not None:
        node.last_reinforced_at = datetime.now(timezone.utc) - timedelta(days=days_since_reinforced)
    else:
        node.last_reinforced_at = None
    return node


@pytest.mark.asyncio
async def test_decay_reduces_weight():
    """Decay after 30 days with 60-day half-life should reduce weight to ~57% of original."""
    node = _make_node(weight=1.0, half_life_days=60, days_since_reinforced=30.0)
    session = AsyncMock()
    session.execute = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [node]
    session.execute.return_value = mock_result

    await apply_decay(uuid.uuid4(), session)

    expected = 1.0 * (0.5 ** (30.0 / 60.0))  # ~0.707
    assert abs(node.weight - expected) < 0.01, f"Expected ~{expected:.3f}, got {node.weight:.3f}"


@pytest.mark.asyncio
async def test_core_node_decays_slower():
    """Core nodes use doubled half-life so they decay more slowly."""
    normal = _make_node(weight=1.0, is_core=False, half_life_days=60, days_since_reinforced=60.0)
    core = _make_node(weight=1.0, is_core=True, half_life_days=60, days_since_reinforced=60.0)

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [normal, core]
    session.execute.return_value = mock_result

    await apply_decay(uuid.uuid4(), session)

    # Normal node: half-life=60, elapsed=60 → 0.5
    # Core node: half-life=120, elapsed=60 → ~0.707
    assert normal.weight < core.weight, "Core node should decay more slowly than non-core"
    assert abs(normal.weight - 0.5) < 0.01
    assert abs(core.weight - 0.5 ** (60.0 / 120.0)) < 0.01


@pytest.mark.asyncio
async def test_weight_floor_prevents_zero():
    """Nodes should not decay below the inactive threshold."""
    node = _make_node(weight=0.001, half_life_days=1, days_since_reinforced=100.0)
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [node]
    session.execute.return_value = mock_result

    await apply_decay(uuid.uuid4(), session)
    assert node.weight >= INACTIVE_WEIGHT_THRESHOLD


@pytest.mark.asyncio
async def test_suppression_expiry_resurfaces_node():
    """When suppression period is over, weight is nudged up and suppressed_until is cleared."""
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    node = _make_node(weight=0.1, suppressed_until=past)
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [node]
    session.execute.return_value = mock_result

    await apply_decay(uuid.uuid4(), session)

    assert node.suppressed_until is None, "suppressed_until should be cleared after expiry"
    assert node.weight > 0.1, "Weight should be nudged up on resurfacing"


@pytest.mark.asyncio
async def test_active_suppression_skips_decay():
    """Nodes still within their suppression window should not be further decayed."""
    future = datetime.now(timezone.utc) + timedelta(days=5)
    node = _make_node(weight=0.2, suppressed_until=future, days_since_reinforced=30.0)
    original_weight = node.weight

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [node]
    session.execute.return_value = mock_result

    await apply_decay(uuid.uuid4(), session)

    assert node.weight == original_weight, "Actively suppressed node weight should be unchanged"
