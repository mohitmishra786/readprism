"""Single-item scoring, kept for callers outside the digest path.

The digest scores all candidates in one pass (`ranker.rank`); this wrapper
runs the same code for one item.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.user import User
from app.services.ranking.contract import SIGNALS
from app.services.ranking.ranker import UserRankingState, rank


async def compute_prs(
    content: ContentItem,
    user: User,
    session: AsyncSession,
    state: UserRankingState | None = None,
) -> tuple[float, dict[str, float]]:
    """(prs, {signal: value}) for one item."""
    scored = await rank(user, [content], session, state=state)
    if not scored:
        return 0.5, {name: 0.5 for name in SIGNALS}
    return scored[0].prs, {name: scored[0].features[name] for name in SIGNALS}
