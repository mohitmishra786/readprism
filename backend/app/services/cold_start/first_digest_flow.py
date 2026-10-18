"""Getting a brand-new user to a non-empty first digest (#102).

Onboarding used to seed sources without fetching them and immediately queue
a digest build, so the first digest was usually empty. The flow is now:

1. `start_first_digest` fetches only this user's sources right away and
   schedules `prepare_first_digest`;
2. `prepare_first_digest` (a Celery task) polls `first_digest_status` and
   builds the digest once enough items are ready, or when the deadline
   passes (it builds with whatever exists rather than never);
3. the web app shows `first_digest_status` as a progress screen.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.digest import Digest
from app.models.source import Source

# Build as soon as this many rankable items exist and most are embedded.
READY_ITEMS = 5
READY_EMBEDDED_SHARE = 0.8
# Build anyway after this long; a thin first digest beats a blank screen.
FIRST_DIGEST_DEADLINE = timedelta(minutes=3)
POLL_SECONDS = 10
WINDOW = timedelta(hours=24)


async def first_digest_status(session: AsyncSession, user_id: uuid.UUID) -> dict:
    from app.services.feed_identity import (
        equivalent_source_ids,
        from_user_feeds,
        user_feed_ids,
        visible_item_filter,
    )

    digest_id = (
        await session.execute(
            select(Digest.id)
            .where(Digest.user_id == user_id)
            .order_by(Digest.generated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    own = (
        await session.execute(
            select(
                func.count(Source.id),
                func.count(Source.last_fetched_at),
            ).where(Source.user_id == user_id, Source.is_active == True)
        )
    ).one()
    sources_total, sources_fetched = int(own[0]), int(own[1])

    source_ids = await equivalent_source_ids(session, user_id)
    feed_ids = await user_feed_ids(session, user_id)
    items = embedded = summarized = 0
    if source_ids or feed_ids:
        row = (
            await session.execute(
                select(
                    func.count(ContentItem.id),
                    func.count(ContentItem.embedding),
                    func.count(ContentItem.summary_brief),
                ).where(
                    from_user_feeds(source_ids, feed_ids),
                    ContentItem.fetched_at >= datetime.now(UTC) - WINDOW,
                    ContentItem.rankable.is_(True),
                    visible_item_filter(user_id),
                )
            )
        ).one()
        items, embedded, summarized = int(row[0]), int(row[1]), int(row[2])

    return {
        "sources_total": sources_total,
        "sources_fetched": sources_fetched,
        "items": items,
        "items_embedded": embedded,
        "items_summarized": summarized,
        "ready": is_ready(items, embedded),
        "digest_id": str(digest_id) if digest_id else None,
    }


def is_ready(items: int, embedded: int) -> bool:
    return items >= READY_ITEMS and embedded >= min(items, READY_ITEMS) * READY_EMBEDDED_SHARE


async def start_first_digest(user_id: uuid.UUID) -> bool:
    """Kick off the first-digest flow once per user. Returns False if already started."""
    from app.utils.cache import cache_set_nx
    from app.workers.tasks.build_digest import prepare_first_digest
    from app.workers.tasks.ingest_feeds import ingest_user_sources

    if not await cache_set_nx(f"first-digest-started:{user_id}", 1, ttl_seconds=3600):
        return False
    deadline = (datetime.now(UTC) + FIRST_DIGEST_DEADLINE).isoformat()
    ingest_user_sources.delay(str(user_id))
    prepare_first_digest.apply_async(args=[str(user_id), deadline], countdown=POLL_SECONDS)
    return True
