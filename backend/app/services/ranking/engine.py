from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.user import User
from app.services.ranking.scorer import compute_prs, load_ranking_context
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def rank_content_for_user(
    user: User,
    content_items: list[ContentItem],
    session: AsyncSession,
    limit: int = 100,
) -> list[tuple[ContentItem, float, dict]]:
    """Score every candidate with the user's current weights and return the top `limit`.

    Every item is scored live and returns its full signal breakdown (#99).
    Reusing precomputed `prs_score`s used to drop the breakdown, so most
    digest items had no explanation and empty impression features, and the
    scores were stale (weights at precompute time). The user's weights,
    history and interest graph are loaded once for the whole batch, and
    items are scored sequentially: one AsyncSession is not safe for
    concurrent use.
    """
    if not content_items:
        return []

    ctx = await load_ranking_context(user, session)
    results: list[tuple[ContentItem, float, dict]] = []
    for item in content_items:
        try:
            prs, breakdown = await compute_prs(item, user, session, ctx)
        except Exception as e:
            logger.warning(f"PRS computation failed for {item.id}: {e}")
            prs, breakdown = 0.0, {}
        results.append((item, prs, breakdown))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:limit]
