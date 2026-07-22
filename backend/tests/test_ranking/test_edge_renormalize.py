"""Nightly edge-weight renormalization in the decay job (audit 04-7)."""

from __future__ import annotations

import pytest

from app.models.interest_graph import InterestEdge, InterestNode
from app.models.user import User
from app.services.interest_graph.decay import renormalize_edges


@pytest.mark.asyncio
async def test_renormalize_edges_uses_current_max(db_session):
    user = User(email="e@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    nodes = [InterestNode(user_id=user.id, topic_label=f"t{i}", weight=0.5) for i in range(3)]
    db_session.add_all(nodes)
    await db_session.flush()

    # Two edges with stale edge_weights that don't reflect the current max count.
    e1 = InterestEdge(
        user_id=user.id,
        from_node_id=nodes[0].id,
        to_node_id=nodes[1].id,
        co_occurrence_count=2,
        edge_weight=1.0,  # stale
    )
    e2 = InterestEdge(
        user_id=user.id,
        from_node_id=nodes[0].id,
        to_node_id=nodes[2].id,
        co_occurrence_count=8,
        edge_weight=0.1,  # stale
    )
    db_session.add_all([e1, e2])
    await db_session.commit()

    count = await renormalize_edges(user.id, db_session)
    assert count == 2

    await db_session.refresh(e1)
    await db_session.refresh(e2)
    # max co_occurrence_count is 8 -> weights become count / 8
    assert e1.edge_weight == pytest.approx(2 / 8)
    assert e2.edge_weight == pytest.approx(8 / 8)
