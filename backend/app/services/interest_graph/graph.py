from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interest_graph import InterestEdge, InterestNode
from app.utils.cache import cache_delete, cache_get, cache_set
from app.utils.logging import get_logger

logger = get_logger(__name__)

CORE_WEIGHT_THRESHOLD = 0.7
CORE_REINFORCEMENT_THRESHOLD = 20


class InterestGraphManager:
    async def get_or_create_node(
        self,
        user_id: uuid.UUID,
        topic_label: str,
        topic_embedding: list[float] | None,
        session: AsyncSession,
    ) -> InterestNode:
        result = await session.execute(
            select(InterestNode).where(
                InterestNode.user_id == user_id,
                InterestNode.topic_label == topic_label,
            )
        )
        node = result.scalar_one_or_none()
        if node is not None:
            return node

        node = InterestNode(
            user_id=user_id,
            topic_label=topic_label,
            topic_embedding=topic_embedding,
            weight=0.1,
        )
        session.add(node)
        await session.flush()
        return node

    async def reinforce_node(
        self,
        node: InterestNode,
        signal_strength: float,
        session: AsyncSession,
    ) -> None:
        if signal_strength > 0:
            node.weight = min(1.0, node.weight + signal_strength * 0.1)
        else:
            node.weight = max(0.0, node.weight + signal_strength * 0.1)

        node.last_reinforced_at = datetime.now(timezone.utc)
        node.reinforcement_count = (node.reinforcement_count or 0) + 1

        if (
            node.weight > CORE_WEIGHT_THRESHOLD
            and node.reinforcement_count >= CORE_REINFORCEMENT_THRESHOLD
        ):
            node.is_core = True

        # Invalidate user interest vector cache
        await cache_delete(f"interest_vec:{node.user_id}")
        await session.flush()

    async def reinforce_edge(
        self,
        user_id: uuid.UUID,
        node_a_id: uuid.UUID,
        node_b_id: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        # Canonical ordering
        from_id, to_id = (node_a_id, node_b_id) if node_a_id < node_b_id else (node_b_id, node_a_id)

        result = await session.execute(
            select(InterestEdge).where(
                InterestEdge.user_id == user_id,
                InterestEdge.from_node_id == from_id,
                InterestEdge.to_node_id == to_id,
            )
        )
        edge = result.scalar_one_or_none()
        if edge is None:
            edge = InterestEdge(
                user_id=user_id,
                from_node_id=from_id,
                to_node_id=to_id,
                co_occurrence_count=0,
                edge_weight=0.0,
            )
            session.add(edge)
            await session.flush()

        edge.co_occurrence_count += 1

        # Normalize: edge_weight = count / max_count for this user
        max_result = await session.execute(
            select(func.max(InterestEdge.co_occurrence_count)).where(
                InterestEdge.user_id == user_id
            )
        )
        max_count = max_result.scalar() or 1
        edge.edge_weight = edge.co_occurrence_count / max_count
        await session.flush()

    async def build_user_interest_vector(
        self, user_id: uuid.UUID, session: AsyncSession
    ) -> Optional[np.ndarray]:
        cache_key = f"interest_vec:{user_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return np.array(cached, dtype=np.float32)

        result = await session.execute(
            select(InterestNode).where(
                InterestNode.user_id == user_id,
                InterestNode.topic_embedding.isnot(None),
            )
        )
        nodes = list(result.scalars().all())
        if not nodes:
            return None

        weights = np.array([n.weight for n in nodes], dtype=np.float32)
        embeddings = np.array([n.topic_embedding for n in nodes], dtype=np.float32)
        weighted = (embeddings * weights[:, np.newaxis]).sum(axis=0)
        norm = np.linalg.norm(weighted)
        if norm > 0:
            weighted = weighted / norm

        await cache_set(cache_key, weighted.tolist(), ttl_seconds=3600)
        return weighted
