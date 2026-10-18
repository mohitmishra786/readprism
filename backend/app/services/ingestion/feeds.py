"""Attach subscriptions to shared feeds and mirror poll state back (#161, #162)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feed import MIRRORED_FIELDS, Feed
from app.models.source import Source


def feed_key_of(source: Source) -> str:
    return source.feed_url or source.url


async def sync_feeds(session: AsyncSession, *, user_id: uuid.UUID | None = None) -> int:
    """Give every active non-newsletter source without a feed its shared feed.

    New subscriptions are created in many places (manual add, packs, OPML,
    sidecar, onboarding, suggestions); attaching them here, before each
    ingest, keeps all of those unchanged. Returns how many were attached.
    """
    query = select(Source).where(
        Source.feed_id.is_(None),
        Source.is_active == True,
        Source.source_type != "newsletter",
    )
    if user_id is not None:
        query = query.where(Source.user_id == user_id)
    pending = list((await session.execute(query)).scalars())
    attached = 0
    from app.services.ingestion.schedule import REDDIT_UNSUPPORTED_NOTICE, is_reddit_feed

    for source in pending:
        key = feed_key_of(source)
        reddit = is_reddit_feed(key)
        feed = (await session.execute(select(Feed).where(Feed.key == key))).scalar_one_or_none()
        if feed is None:
            feed = Feed(
                key=key,
                url=source.url,
                feed_url=source.feed_url,
                source_type=source.source_type or "rss",
                is_active=not reddit,
                last_fetched_at=source.last_fetched_at,
                http_etag=source.http_etag,
                http_last_modified=source.http_last_modified,
                poll_interval_seconds=source.poll_interval_seconds or 3600,
                next_poll_at=None if reddit else source.next_poll_at,
                recent_gap_seconds=list(source.recent_gap_seconds or []),
                feed_status="dead" if reddit else (source.feed_status or "healthy"),
                last_error=REDDIT_UNSUPPORTED_NOTICE if reddit else source.last_error,
                last_error_at=datetime.now(UTC) if reddit else source.last_error_at,
                dead_notice_pending=reddit,
                fetch_error_count=source.fetch_error_count or 0,
                initial_backfill_done=bool(source.initial_backfill_done),
            )
            session.add(feed)
            await session.flush()
        elif not feed.is_active and not reddit:
            # A dead feed someone subscribes to again gets a fresh chance.
            feed.is_active = True
            feed.feed_status = "healthy"
            feed.next_poll_at = None
        source.feed_id = feed.id
        if reddit:
            source.is_active = False
            source.dead_notice_pending = True
            source.feed_status = "dead"
            source.last_error = REDDIT_UNSUPPORTED_NOTICE
        attached += 1
    if attached:
        await session.flush()
    return attached


async def subscribers(
    session: AsyncSession, feed_id: uuid.UUID, *, active_only: bool = True
) -> list[Source]:
    query = select(Source).where(Source.feed_id == feed_id)
    if active_only:
        query = query.where(Source.is_active == True)
    return list(
        (await session.execute(query.order_by(Source.created_at.asc(), Source.id.asc()))).scalars()
    )


def mirror(feed: Feed, sources: list[Source]) -> None:
    """Copy the feed's poll state onto its subscribers' rows.

    When the feed has just died, each subscriber's source is paused and gets
    its one-time dead-feed notice, as single-user sources did before.
    """
    for source in sources:
        for name in MIRRORED_FIELDS:
            setattr(source, name, getattr(feed, name))
        if not feed.is_active and source.is_active:
            source.is_active = False
            source.dead_notice_pending = True
