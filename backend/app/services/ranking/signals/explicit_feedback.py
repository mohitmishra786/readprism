from __future__ import annotations

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.services.ranking.signals import UserInterestGraph
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def compute(
    content: ContentItem,
    user: User,
    interaction_history: list[UserContentInteraction],
    interest_graph: UserInterestGraph,
    session: AsyncSession,
) -> float:
    rated = [i for i in interaction_history if i.explicit_rating is not None]
    if not rated or content.embedding is None:
        return 0.5

    content_vec = np.array(content.embedding, dtype=np.float32)
    positive_ids = [str(i.content_item_id) for i in rated if i.explicit_rating == 1]
    negative_ids = [str(i.content_item_id) for i in rated if i.explicit_rating == -1]

    positive_sim = await _mean_similarity(content_vec, positive_ids, session)
    negative_sim = await _mean_similarity(content_vec, negative_ids, session)

    score = 0.5 + (positive_sim * 0.5) - (negative_sim * 0.5)

    # Apply rating reason adjustments
    too_basic_reasons = [
        i for i in rated if i.explicit_rating_reason == "too_basic" and i.explicit_rating == -1
    ]
    too_tangential_reasons = [
        i for i in rated if i.explicit_rating_reason == "too_tangential" and i.explicit_rating == -1
    ]

    if too_basic_reasons and content.content_depth_score is not None and content.content_depth_score < 0.4:
        score -= 0.1

    if too_tangential_reasons:
        core_nodes = sorted(interest_graph.nodes, key=lambda n: n.weight, reverse=True)[:3]
        core_labels = {n.topic_label for n in core_nodes}
        if content.topic_clusters and not any(t in core_labels for t in content.topic_clusters):
            score -= 0.1

    return float(np.clip(score, 0.0, 1.0))


async def _mean_similarity(
    content_vec: np.ndarray, item_ids: list[str], session: AsyncSession
) -> float:
    if not item_ids:
        return 0.0
    try:
        result = await session.execute(
            text("SELECT embedding FROM content_items WHERE id = ANY(:ids) AND embedding IS NOT NULL"),
            {"ids": item_ids},
        )
        rows = result.fetchall()
        if not rows:
            return 0.0
        sims = []
        for row in rows:
            emb = np.array(row[0], dtype=np.float32)
            sim = float(np.dot(content_vec, emb) / (np.linalg.norm(content_vec) * np.linalg.norm(emb) + 1e-8))
            sims.append((sim + 1.0) / 2.0)
        return float(np.mean(sims))
    except Exception as e:
        logger.warning(f"explicit_feedback similarity query failed: {e}")
        return 0.0
