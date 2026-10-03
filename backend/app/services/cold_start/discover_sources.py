"""Discover-source engine (EC-06): candidate mining + accept/dismiss loop."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.source import Source
from app.models.suggestion import SourceSuggestion
from app.models.user import User
from app.utils.logging import get_logger

logger = get_logger(__name__)

MAX_PENDING = 5


async def refresh_suggestions(user: User, session: AsyncSession) -> int:
    """Insert new pending suggestions; returns the number added.

    Sources of discovery items the user fully read come first (the spec's
    suggestion loop), then starter-pack feeds matching top interest clusters.
    URLs with ANY prior row (pending/accepted/dismissed) never re-enter —
    dismissals are permanent.
    """
    existing = await session.execute(
        select(SourceSuggestion.url).where(SourceSuggestion.user_id == user.id)
    )
    known_urls = {row[0] for row in existing.fetchall()}

    followed = await session.execute(select(Source.url).where(Source.user_id == user.id))
    known_urls |= {row[0] for row in followed.fetchall()}

    candidates: list[tuple[str, str, str]] = []  # (url, name, reason)

    # (a) Unfollowed sources whose discovery items were fully read.
    rows = await session.execute(
        select(ContentItem.source_id, ContentItem.url, ContentItem.title)
        .join(
            UserContentInteraction,
            (
                (UserContentInteraction.content_item_id == ContentItem.id)
                & (UserContentInteraction.user_id == user.id)
            ),
        )
        .where(
            ContentItem.origin == "discovery",
            UserContentInteraction.read_completion_pct >= 0.85,
        )
        .limit(50)
    )
    seen_sources: set[object] = set()
    for source_id, _url, title in rows.fetchall():
        if source_id is None or source_id in seen_sources:
            continue
        seen_sources.add(source_id)
        src = (
            await session.execute(select(Source).where(Source.id == source_id))
        ).scalar_one_or_none()
        if src is not None and src.url not in known_urls:
            candidates.append((src.url, src.name or src.url, f"You fully read {title[:60]}"))
            known_urls.add(src.url)

    # (b) Starter-pack feeds matching the user's top interest clusters.
    from app.models.interest_graph import InterestNode

    nodes = await session.execute(
        select(InterestNode.topic_label)
        .where(InterestNode.user_id == user.id)
        .order_by(InterestNode.weight.desc())
        .limit(5)
    )
    top_topics = [row[0].lower() for row in nodes.fetchall()]

    from app.services.cold_start.starter_packs import list_starter_packs

    for pack in list_starter_packs():
        pack_words = set(pack.id.replace("-", " ").lower().split())
        if top_topics and not any(
            word in pack_words for topic in top_topics for word in topic.split()
        ):
            continue
        for feed in pack.feeds:
            if feed["url"] not in known_urls and len(candidates) < MAX_PENDING + len(known_urls):
                candidates.append(
                    (feed["url"], feed["name"], f"Matches your {pack.title} interests")
                )
                known_urls.add(feed["url"])
        if len(candidates) >= 30:
            break

    added = 0
    pending_count = (
        await session.execute(
            select(SourceSuggestion.id).where(
                SourceSuggestion.user_id == user.id, SourceSuggestion.status == "pending"
            )
        )
    ).fetchall()
    room = max(0, MAX_PENDING - len(pending_count))
    for url, name, reason in candidates[:room]:
        session.add(
            SourceSuggestion(user_id=user.id, url=url, name=name[:200], reason=reason[:200])
        )
        added += 1
    if added:
        await session.flush()
        logger.info(f"Added {added} source suggestions for user {user.id}")
    return added
