from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.user import User
from app.services.ranking.ranker import rank


async def rank_content_for_user(
    user: User,
    content_items: list[ContentItem],
    session: AsyncSession,
    limit: int = 100,
) -> list[tuple[ContentItem, float, dict]]:
    """Score every candidate with the user's current state; best `limit` first.

    One vectorized pass (#129): the user's weights, history and interest graph
    are loaded once, and every item gets its full breakdown, contributions and
    explanation (#99, #143).
    """
    scored = await rank(user, content_items, session)
    return [(s.item, s.prs, s.breakdown()) for s in scored[:limit]]
