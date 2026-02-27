from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.source import Source
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
    if content.source_id is None:
        return 0.4

    result = await session.execute(select(Source).where(Source.id == content.source_id))
    source = result.scalar_one_or_none()
    if source is None:
        return 0.4

    return float(max(0.0, min(1.0, source.trust_weight)))
