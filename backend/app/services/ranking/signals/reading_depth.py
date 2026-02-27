from __future__ import annotations

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.services.ranking.signals import UserInterestGraph
from app.utils.logging import get_logger

logger = get_logger(__name__)
MIN_HISTORY = 5


async def compute(
    content: ContentItem,
    user: User,
    interaction_history: list[UserContentInteraction],
    interest_graph: UserInterestGraph,
    session: AsyncSession,
) -> float:
    interactions_with_completion = [
        i for i in interaction_history if i.read_completion_pct is not None
    ]

    if len(interactions_with_completion) < MIN_HISTORY:
        return 0.5

    if content.embedding is None:
        return 0.5

    content_vec = np.array(content.embedding, dtype=np.float32)

    # pgvector similarity query for top-20 most similar interacted items
    try:
        result = await session.execute(
            text("""
                SELECT ci.embedding, uci.read_completion_pct
                FROM content_items ci
                JOIN user_content_interactions uci ON ci.id = uci.content_item_id
                WHERE uci.user_id = :user_id
                  AND uci.read_completion_pct IS NOT NULL
                  AND ci.embedding IS NOT NULL
                ORDER BY ci.embedding <=> CAST(:embedding AS vector)
                LIMIT 20
            """),
            {"user_id": str(user.id), "embedding": str(content.embedding)},
        )
        rows = result.fetchall()
    except Exception as e:
        logger.warning(f"reading_depth pgvector query failed: {e}")
        return 0.5

    if not rows:
        return 0.5

    similarities = []
    completions = []
    for row in rows:
        emb_raw, completion = row
        if emb_raw is None:
            continue
        emb = np.array(emb_raw, dtype=np.float32)
        sim = float(np.dot(content_vec, emb) / (np.linalg.norm(content_vec) * np.linalg.norm(emb) + 1e-8))
        sim = (sim + 1.0) / 2.0
        similarities.append(sim)
        completions.append(float(completion))

    if not similarities:
        return 0.5

    weights = np.array(similarities)
    completions_arr = np.array(completions)
    weighted_avg = float(np.dot(weights, completions_arr) / (weights.sum() + 1e-8))
    return float(np.clip(weighted_avg, 0.0, 1.0))
