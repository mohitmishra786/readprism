"""Collaborative warmup for new users, from crowd signals only (#210).

A new reader with chosen topics gets a few items that many readers on this
instance recently finished or upvoted. Privacy rules:

- k-anonymity: an item is eligible only when at least
  `COLLABORATIVE_K_ANONYMITY` distinct users (default 20) engaged with it, so
  no recommendation can be traced to one person's reading;
- the selection never looks at any individual's history or interest vector,
  only at per-item counts;
- users who opt out (`collaborative_opt_out`) are left out of the counts;
- private items (newsletters, saves) never qualify.

Eligible items are then matched to the newcomer's own interests (topic
labels and, when available, their interest vector). Below
`COLLABORATIVE_WARMUP_MIN_USERS` active readers this is inert; on a
single-user or family instance k is never met.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.content import ContentItem, UserContentInteraction
from app.models.interest_graph import InterestNode
from app.models.user import User
from app.services.interest_graph.graph import InterestGraphManager
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()
graph_manager = InterestGraphManager()

MIN_COMPLETION_FOR_POSITIVE = 0.85
WINDOW = timedelta(days=14)
CANDIDATES = 200


def _words(text: str) -> set[str]:
    return {w for w in text.lower().replace("&", " ").replace("-", " ").split() if len(w) > 2}


def _topic_score(item: ContentItem, labels: list[str]) -> float:
    clusters = [str(c).lower() for c in (item.topic_clusters or [])]
    if not clusters or not labels:
        return 0.0
    if set(clusters) & set(labels):
        return 1.0
    label_words = set().union(*(_words(label) for label in labels))
    cluster_words = set().union(*(_words(c) for c in clusters))
    return 0.5 if label_words & cluster_words else 0.0


async def crowd_items(
    session: AsyncSession, *, exclude_user, now: datetime | None = None
) -> list[tuple[ContentItem, int]]:
    """Public items at least k distinct, non-opted-out users engaged with recently."""
    k = max(1, settings.collaborative_k_anonymity)
    since = (now or datetime.now(UTC)) - WINDOW
    readers = func.count(func.distinct(UserContentInteraction.user_id))
    rows = (
        await session.execute(
            select(ContentItem, readers)
            .join(UserContentInteraction, UserContentInteraction.content_item_id == ContentItem.id)
            .join(User, User.id == UserContentInteraction.user_id)
            .where(
                ContentItem.owner_user_id.is_(None),
                ContentItem.rankable.is_(True),
                UserContentInteraction.user_id != exclude_user,
                User.collaborative_opt_out.is_(False),
                UserContentInteraction.updated_at >= since,
                (UserContentInteraction.explicit_rating == 1)
                | (UserContentInteraction.read_completion_pct >= MIN_COMPLETION_FOR_POSITIVE),
            )
            .group_by(ContentItem.id)
            .having(readers >= k)
            .order_by(readers.desc())
            .limit(CANDIDATES)
        )
    ).all()
    return [(item, int(count)) for item, count in rows]


async def get_collaborative_warmup_items(
    user: User,
    limit: int,
    session: AsyncSession,
) -> list[ContentItem]:
    if not settings.cold_start_collaborative_enabled:
        return []

    active_users = (
        await session.execute(select(func.count(func.distinct(UserContentInteraction.user_id))))
    ).scalar() or 0
    if active_users < settings.collaborative_warmup_min_users:
        logger.debug(
            f"Collaborative warmup skipped: {active_users} active users < "
            f"{settings.collaborative_warmup_min_users} threshold"
        )
        return []

    candidates = await crowd_items(session, exclude_user=user.id)
    if not candidates:
        return []

    labels = [
        row[0].lower()
        for row in (
            await session.execute(
                select(InterestNode.topic_label)
                .where(InterestNode.user_id == user.id)
                .order_by(InterestNode.weight.desc())
                .limit(10)
            )
        ).all()
    ]
    user_vec = await graph_manager.build_user_interest_vector(user.id, session)
    if not labels and user_vec is None:
        return []  # nothing to match against; don't push generic popularity

    top = max(count for _, count in candidates)
    scored: list[tuple[float, ContentItem]] = []
    for item, count in candidates:
        relevance = _topic_score(item, labels)
        if user_vec is not None and item.embedding is not None:
            emb = np.asarray(item.embedding, dtype=np.float32)
            cosine = float(
                np.dot(user_vec, emb) / (np.linalg.norm(user_vec) * np.linalg.norm(emb) + 1e-8)
            )
            relevance = max(relevance, cosine)
        if relevance <= 0.3:
            continue
        scored.append((relevance + 0.2 * count / top, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:limit]]
