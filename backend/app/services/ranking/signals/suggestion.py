from __future__ import annotations

from datetime import datetime, timezone, timedelta

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.services.ranking.signals import UserInterestGraph
from app.utils.logging import get_logger

logger = get_logger(__name__)
SUGGESTION_SIMILARITY_THRESHOLD = 0.75
BOOST_FACTOR = 1.3
MIN_USER_DAYS = 14


async def compute(
    content: ContentItem,
    user: User,
    interaction_history: list[UserContentInteraction],
    interest_graph: UserInterestGraph,
    session: AsyncSession,
) -> float:
    # Only meaningful after 2+ weeks of usage
    user_age_days = (datetime.now(timezone.utc) - user.created_at.replace(tzinfo=timezone.utc)).days
    if user_age_days < MIN_USER_DAYS:
        return 0.5

    if content.embedding is None:
        return 0.5

    content_vec = np.array(content.embedding, dtype=np.float32)

    # Find interactions where item was suggested and fully read
    high_value = [
        i for i in interaction_history
        if i.was_suggested and i.read_completion_pct is not None and i.read_completion_pct >= 0.85
    ]

    if not high_value:
        return 0.5

    max_similarity = 0.0

    # Query embeddings for suggestion-read items
    from sqlalchemy import select, text
    try:
        ids = [str(i.content_item_id) for i in high_value]
        result = await session.execute(
            text("""
                SELECT ci.embedding
                FROM content_items ci
                WHERE ci.id = ANY(:ids) AND ci.embedding IS NOT NULL
            """),
            {"ids": ids},
        )
        rows = result.fetchall()
        for row in rows:
            emb = np.array(row[0], dtype=np.float32)
            sim = float(np.dot(content_vec, emb) / (np.linalg.norm(content_vec) * np.linalg.norm(emb) + 1e-8))
            sim = (sim + 1.0) / 2.0
            if sim > max_similarity:
                max_similarity = sim
    except Exception as e:
        logger.warning(f"suggestion signal query failed: {e}")
        return 0.5

    if max_similarity > SUGGESTION_SIMILARITY_THRESHOLD:
        return min(1.0, max_similarity * BOOST_FACTOR)
    return 0.5
