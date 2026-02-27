from __future__ import annotations

import uuid
from typing import Optional

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.services.interest_graph.graph import InterestGraphManager
from app.utils.cache import cache_get
from app.utils.logging import get_logger

logger = get_logger(__name__)
graph_manager = InterestGraphManager()

SIMILAR_USERS_COUNT = 10
MIN_COMPLETION_FOR_POSITIVE = 0.85


async def get_collaborative_warmup_items(
    user: User,
    limit: int,
    session: AsyncSession,
) -> list[ContentItem]:
    # Get user's interest vector
    user_vec = await graph_manager.build_user_interest_vector(user.id, session)
    if user_vec is None:
        return []

    # Find 10 similar users via pgvector similarity
    try:
        result = await session.execute(
            text("""
                SELECT DISTINCT uci.user_id
                FROM user_content_interactions uci
                WHERE uci.user_id != :user_id
                LIMIT 200
            """),
            {"user_id": str(user.id)},
        )
        candidate_user_ids = [row[0] for row in result.fetchall()]
    except Exception as e:
        logger.warning(f"Collaborative warmup user query failed: {e}")
        return []

    if not candidate_user_ids:
        return []

    # Compute similarity with each candidate user
    user_sims: list[tuple[str, float]] = []
    for cuid in candidate_user_ids:
        other_vec = await cache_get(f"interest_vec:{cuid}")
        if other_vec is None:
            continue
        other = np.array(other_vec, dtype=np.float32)
        sim = float(np.dot(user_vec, other) / (np.linalg.norm(user_vec) * np.linalg.norm(other) + 1e-8))
        user_sims.append((cuid, sim))

    user_sims.sort(key=lambda x: x[1], reverse=True)
    top_users = [uid for uid, _ in user_sims[:SIMILAR_USERS_COUNT]]

    if not top_users:
        return []

    # Collect positively interacted items from similar users
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    try:
        result = await session.execute(
            text("""
                SELECT ci.*, COUNT(*) as engagement_count
                FROM content_items ci
                JOIN user_content_interactions uci ON ci.id = uci.content_item_id
                WHERE uci.user_id = ANY(:user_ids)
                  AND uci.created_at >= :cutoff
                  AND (uci.explicit_rating = 1 OR uci.read_completion_pct >= :min_completion)
                GROUP BY ci.id
                ORDER BY engagement_count DESC
                LIMIT :limit
            """),
            {
                "user_ids": top_users,
                "cutoff": cutoff,
                "min_completion": MIN_COMPLETION_FOR_POSITIVE,
                "limit": limit * 2,
            },
        )
        rows = result.fetchall()
    except Exception as e:
        logger.warning(f"Collaborative items query failed: {e}")
        return []

    # Load full content items
    if not rows:
        return []

    item_ids = [row[0] for row in rows][:limit]
    items_result = await session.execute(
        select(ContentItem).where(ContentItem.id.in_(item_ids))
    )
    return list(items_result.scalars().all())
