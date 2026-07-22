from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interest_graph import InterestEdge, InterestNode
from app.utils.logging import get_logger

logger = get_logger(__name__)
INACTIVE_WEIGHT_THRESHOLD = 0.05


async def renormalize_edges(user_id: uuid.UUID, session: AsyncSession) -> int:
    """Recompute every edge_weight as co_occurrence_count / max_count for the user.

    Per-reinforcement normalization only updates the touched edge, so other
    edges' weights go stale relative to a moving max. This nightly pass corrects
    all of them at once (audit 04-7). Returns the number of edges renormalized.
    """
    max_count = (
        await session.execute(
            select(func.max(InterestEdge.co_occurrence_count)).where(
                InterestEdge.user_id == user_id
            )
        )
    ).scalar() or 1

    edges = list(
        (
            await session.execute(select(InterestEdge).where(InterestEdge.user_id == user_id))
        ).scalars()
    )
    for edge in edges:
        edge.edge_weight = edge.co_occurrence_count / max_count
    await session.flush()
    return len(edges)


async def apply_decay(user_id: uuid.UUID, session: AsyncSession) -> None:
    result = await session.execute(select(InterestNode).where(InterestNode.user_id == user_id))
    nodes = list(result.scalars().all())

    now = datetime.now(UTC)
    for node in nodes:
        # Handle time-bounded suppression: gently resurface when period expires
        if node.suppressed_until is not None:
            sup = node.suppressed_until
            if sup.tzinfo is None:
                sup = sup.replace(tzinfo=UTC)
            if now >= sup:
                # Suppression period over — clear flag and nudge weight up slightly
                node.suppressed_until = None
                node.weight = min(0.4, node.weight + 0.1)
            else:
                # Still suppressed — skip decay entirely (weight already penalised)
                continue

        if node.last_reinforced_at is None:
            continue

        last = node.last_reinforced_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)

        days_elapsed = (now - last).total_seconds() / 86400.0
        half_life = float(node.half_life_days)

        # Core nodes get doubled half-life during decay
        if node.is_core:
            half_life *= 2.0

        if days_elapsed > 0 and half_life > 0:
            decay_factor = 0.5 ** (days_elapsed / half_life)
            node.weight = float(node.weight) * decay_factor

        if node.weight < INACTIVE_WEIGHT_THRESHOLD:
            node.weight = INACTIVE_WEIGHT_THRESHOLD  # keep but nearly inactive

    await session.flush()

    # Correct any edge weights left stale by per-write normalization.
    edge_count = await renormalize_edges(user_id, session)
    logger.info(
        f"Decay applied to {len(nodes)} nodes, renormalized {edge_count} edges for user {user_id}"
    )
