from __future__ import annotations

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
    from app.services.feed_identity import user_source_for_item

    # The user's own trust for this feed, not that of whichever subscriber's
    # source happens to hold the shared item (#108).
    source = await user_source_for_item(session, user.id, content.source_id)
    if source is None:
        return 0.4

    return float(max(0.0, min(1.0, source.trust_weight)))
