from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interest_graph import InterestNode
from app.utils.logging import get_logger

logger = get_logger(__name__)
INACTIVE_WEIGHT_THRESHOLD = 0.05


async def apply_decay(user_id: uuid.UUID, session: AsyncSession) -> None:
    result = await session.execute(
        select(InterestNode).where(InterestNode.user_id == user_id)
    )
    nodes = list(result.scalars().all())

    now = datetime.now(timezone.utc)
    for node in nodes:
        # Handle time-bounded suppression: gently resurface when period expires
        if node.suppressed_until is not None:
            sup = node.suppressed_until
            if sup.tzinfo is None:
                sup = sup.replace(tzinfo=timezone.utc)
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
            last = last.replace(tzinfo=timezone.utc)

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
    logger.info(f"Decay applied to {len(nodes)} nodes for user {user_id}")
