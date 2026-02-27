from __future__ import annotations

import asyncio
import uuid
from typing import Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.interest_graph import InterestEdge, InterestNode
from app.models.user import User
from app.services.ranking.meta_weights import get_meta_weights
from app.services.ranking.signals import UserInterestGraph
from app.services.ranking.signals import (
    content_quality,
    explicit_feedback,
    novelty,
    reading_depth,
    semantic,
    source_trust,
    suggestion,
    temporal_context,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

SIGNAL_MODULES = {
    "semantic": semantic,
    "reading_depth": reading_depth,
    "suggestion": suggestion,
    "explicit_feedback": explicit_feedback,
    "source_trust": source_trust,
    "content_quality": content_quality,
    "temporal_context": temporal_context,
    "novelty": novelty,
}


async def compute_prs(
    content: ContentItem,
    user: User,
    session: AsyncSession,
) -> Tuple[float, dict[str, float]]:
    # Load meta weights
    meta = await get_meta_weights(user.id, session)

    # Load interaction history (last 200)
    history_result = await session.execute(
        select(UserContentInteraction)
        .where(UserContentInteraction.user_id == user.id)
        .order_by(UserContentInteraction.created_at.desc())
        .limit(200)
    )
    interaction_history = list(history_result.scalars().all())

    # Load interest graph
    nodes_result = await session.execute(
        select(InterestNode).where(InterestNode.user_id == user.id)
    )
    edges_result = await session.execute(
        select(InterestEdge).where(InterestEdge.user_id == user.id)
    )
    graph = UserInterestGraph(
        nodes=list(nodes_result.scalars().all()),
        edges=list(edges_result.scalars().all()),
    )

    # Compute all signals in parallel
    tasks = {
        name: mod.compute(content, user, interaction_history, graph, session)
        for name, mod in SIGNAL_MODULES.items()
    }

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    signal_scores: dict[str, float] = {}

    for name, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            logger.warning(f"Signal {name} failed: {result}")
            signal_scores[name] = 0.5  # neutral fallback
        else:
            signal_scores[name] = float(result)

    # Compute weighted PRS
    prs = sum(
        meta.weights.get(name, 0.0) * score
        for name, score in signal_scores.items()
    )
    prs = max(0.0, min(1.0, prs))

    return prs, signal_scores
