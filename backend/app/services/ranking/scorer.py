from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.interest_graph import InterestEdge, InterestNode
from app.models.user import User
from app.services.ranking.meta_weights import UserMetaWeights, get_meta_weights
from app.services.ranking.signals import (
    UserInterestGraph,
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


@dataclass
class RankingContext:
    """Per-user state every item's score needs; loaded once per digest build."""

    meta: UserMetaWeights
    history: list[UserContentInteraction]
    graph: UserInterestGraph


async def load_ranking_context(user: User, session: AsyncSession) -> RankingContext:
    meta = await get_meta_weights(user.id, session)
    history_result = await session.execute(
        select(UserContentInteraction)
        .where(UserContentInteraction.user_id == user.id)
        .order_by(UserContentInteraction.created_at.desc())
        .limit(200)
    )
    nodes_result = await session.execute(
        select(InterestNode).where(InterestNode.user_id == user.id)
    )
    edges_result = await session.execute(
        select(InterestEdge).where(InterestEdge.user_id == user.id)
    )
    return RankingContext(
        meta=meta,
        history=list(history_result.scalars().all()),
        graph=UserInterestGraph(
            nodes=list(nodes_result.scalars().all()),
            edges=list(edges_result.scalars().all()),
        ),
    )


async def compute_prs(
    content: ContentItem,
    user: User,
    session: AsyncSession,
    ctx: RankingContext | None = None,
) -> tuple[float, dict[str, float]]:
    """Score one item. Pass a preloaded `ctx` when scoring many items (#99)."""
    if ctx is None:
        ctx = await load_ranking_context(user, session)
    meta = ctx.meta
    graph = ctx.graph
    # Never let the item's own interaction inform its score (leakage).
    interaction_history = [row for row in ctx.history if row.content_item_id != content.id]

    # Compute signals sequentially. They all query through the same AsyncSession,
    # which is NOT safe to use concurrently (SQLAlchemy async sessions aren't
    # concurrency-safe); a previous asyncio.gather here only appeared parallel
    # because the awaits serialized on the session anyway. Running them in
    # sequence removes that latent bug without a real latency cost (audit 04-2).
    signal_scores: dict[str, float] = {}
    for name, mod in SIGNAL_MODULES.items():
        try:
            result = await mod.compute(content, user, interaction_history, graph, session)
            signal_scores[name] = float(result)
        except Exception as e:
            logger.warning(f"Signal {name} failed: {e}")
            signal_scores[name] = 0.5  # neutral fallback

    # Compute weighted PRS (only numeric signal scores; the breakdown may also
    # carry a non-numeric "why_topics" explanation string).
    prs = sum(
        meta.weights.get(name, 0.0) * score
        for name, score in signal_scores.items()
        if isinstance(score, int | float)
    )
    prs = max(0.0, min(1.0, prs))

    return prs, signal_scores
