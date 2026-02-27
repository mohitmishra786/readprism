from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.services.ranking.signals import UserInterestGraph
from app.utils.cache import cache_get, cache_set
from app.utils.logging import get_logger

logger = get_logger(__name__)

CACHE_TTL = 30 * 24 * 3600  # 30 days


async def compute(
    content: ContentItem,
    user: User,
    interaction_history: list[UserContentInteraction],
    interest_graph: UserInterestGraph,
    session: AsyncSession,
) -> float:
    cache_key = f"quality:{content.id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return float(cached)

    score = _compute_quality(content)
    await cache_set(cache_key, score, ttl_seconds=CACHE_TTL)
    return score


def _compute_quality(content: ContentItem) -> float:
    reading_time = content.reading_time_minutes or 0
    word_count = content.word_count or 0
    has_citations = content.has_citations
    is_original = content.is_original_reporting
    depth = content.content_depth_score

    s_reading = min(1.0, reading_time / 15.0)
    s_words = min(1.0, word_count / 2000.0)
    s_citations = 1.0 if has_citations else 0.3
    s_original = 1.0 if is_original is True else (0.5 if is_original is None else 0.2)
    s_depth = float(depth) if depth is not None else 0.5

    score = (
        s_reading * 0.25
        + s_words * 0.10
        + s_citations * 0.20
        + s_original * 0.25
        + s_depth * 0.20
    )
    return float(max(0.0, min(1.0, score)))
