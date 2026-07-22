from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.services.ranking.signals import UserInterestGraph, cosine_to_unit_score
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def compute(
    content: ContentItem,
    user: User,
    interaction_history: list[UserContentInteraction],
    interest_graph: UserInterestGraph,
    session: AsyncSession,
) -> float:
    if content.embedding is None:
        return 0.5

    cutoff = datetime.now(UTC) - timedelta(days=30)
    try:
        result = await session.execute(
            text(
                """
                SELECT ci.embedding
                FROM content_items ci
                JOIN user_content_interactions uci ON ci.id = uci.content_item_id
                WHERE uci.user_id = :user_id
                  AND uci.created_at >= :cutoff
                  AND ci.id != :content_id
                  AND ci.embedding IS NOT NULL
                LIMIT 100
            """
            ),
            {"user_id": str(user.id), "cutoff": cutoff, "content_id": str(content.id)},
        )
        rows = result.fetchall()
        if not rows:
            return 0.5

        content_vec = np.array(content.embedding, dtype=np.float32)
        max_sim = 0.0
        for row in rows:
            emb = np.array(row[0], dtype=np.float32)
            sim = float(
                np.dot(content_vec, emb)
                / (np.linalg.norm(content_vec) * np.linalg.norm(emb) + 1e-8)
            )
            sim = cosine_to_unit_score(sim)
            if sim > max_sim:
                max_sim = sim

        novelty = 1.0 - max_sim
        # Score peaks at the configured novelty target, falls off at extremes.
        target = settings.novelty_target
        score = 1.0 - abs(novelty - target) / target
        return float(np.clip(score, 0.0, 1.0))
    except Exception as e:
        logger.warning(f"novelty signal query failed: {e}")
        return 0.5
