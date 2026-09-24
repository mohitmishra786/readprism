from __future__ import annotations

import uuid
from datetime import UTC

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.source import Source
from app.services.ingestion.canonicalize import canonicalize_url
from app.services.ingestion.rss_parser import FeedFetchResult, RawContentItem, fetch_feed
from app.services.ingestion.scraper import scrape_page
from app.utils.cache import get_redis
from app.utils.logging import get_logger

logger = get_logger(__name__)

SEMANTIC_DEDUP_THRESHOLD = 0.92  # cosine similarity above which items are considered duplicates


def _remember_validators(source: Source, fetched: FeedFetchResult) -> None:
    """Keep the validators the server just sent. A 304 often omits them."""
    if fetched.etag:
        source.http_etag = fetched.etag
    if fetched.last_modified:
        source.http_last_modified = fetched.last_modified


async def dispatch_source(source: Source, session: AsyncSession) -> list[RawContentItem]:
    raw_items: list[RawContentItem] = []

    if source.source_type == "newsletter":
        raw_items = await _fetch_newsletter_items(source, session)
    elif source.feed_url or source.source_type == "rss":
        feed_url = source.feed_url or source.url
        fetched = await fetch_feed(
            feed_url,
            etag=getattr(source, "http_etag", None),
            last_modified=getattr(source, "http_last_modified", None),
        )
        _remember_validators(source, fetched)
        source.last_http_status = fetched.status_code  # type: ignore[attr-defined]
        raw_items = [] if fetched.not_modified else fetched.items
        if not raw_items and not fetched.not_modified and source.feed_url is None:
            # Try autodiscovery
            from app.services.ingestion.rss_parser import _autodiscover_feed

            discovered = await _autodiscover_feed(source.url)
            if discovered:
                fetched = await fetch_feed(discovered)
                _remember_validators(source, fetched)
                raw_items = fetched.items
                if raw_items:
                    source.feed_url = discovered
                    await session.flush()
    elif source.source_type == "scraped":
        item = await scrape_page(source.url)
        if item:
            raw_items = [item]

    # Deduplicate against existing URLs
    if not raw_items:
        return []

    collapsed: list[RawContentItem] = []
    seen_urls: set[str] = set()
    for item in raw_items:
        canonical = canonicalize_url(item.url)
        if canonical is None or canonical in seen_urls:
            continue
        item.url = canonical
        seen_urls.add(canonical)
        collapsed.append(item)
    raw_items = collapsed
    stored = await session.execute(
        select(ContentItem.url).where(ContentItem.source_id == source.id)
    )
    existing_urls: set[str] = set()
    for row in stored.fetchall():
        canonical = canonicalize_url(row[0])
        if canonical:
            existing_urls.add(canonical)
    new_items = [item for item in raw_items if item.url not in existing_urls]

    logger.info(
        f"Source {source.id}: {len(raw_items)} fetched, {len(new_items)} new after URL dedup"
    )
    return new_items


async def semantic_dedup(
    item_id: uuid.UUID,
    embedding: list[float],
    session: AsyncSession,
    window_hours: int = 72,
    owner_user_id: uuid.UUID | None = None,
) -> bool:
    """Return True if a semantically similar item already exists in the recent queue.

    Comparison is scoped so private content (a user's newsletters) is only
    deduped against public content or that same user's content — never against
    another tenant's private items (audit 06-6).
    """
    from datetime import datetime, timedelta

    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    try:
        result = await session.execute(
            text(
                """
                SELECT id, embedding <=> CAST(:emb AS vector) AS dist
                FROM content_items
                WHERE fetched_at >= :cutoff
                  AND id != :item_id
                  AND embedding IS NOT NULL
                  AND (owner_user_id IS NULL OR owner_user_id = :owner)
                ORDER BY dist ASC
                LIMIT 1
            """
            ),
            {
                "emb": str(embedding),
                "cutoff": cutoff,
                "item_id": str(item_id),
                "owner": str(owner_user_id) if owner_user_id else None,
            },
        )
        row = result.fetchone()
        if row is None:
            return False
        cosine_similarity = 1.0 - float(row[1])
        return cosine_similarity >= SEMANTIC_DEDUP_THRESHOLD
    except Exception as e:
        logger.debug(f"Semantic dedup query failed (non-fatal): {e}")
        return False


async def _fetch_newsletter_items(source: Source, session: AsyncSession) -> list[RawContentItem]:
    redis = get_redis()
    pattern = f"newsletter:{source.user_id}:*"
    items: list[RawContentItem] = []
    try:
        import json

        async for key in redis.scan_iter(pattern):
            data_str = await redis.get(key)
            if data_str:
                data = json.loads(data_str)
                msg_id = data.get("message_id", str(key))
                items.append(
                    RawContentItem(
                        url=f"newsletter://{source.user_id}/{msg_id}",
                        title=data.get("subject", "Newsletter"),
                        author=data.get("sender"),
                        full_text=data.get("body"),
                        word_count=len(data.get("body", "").split()) if data.get("body") else None,
                    )
                )
    except Exception as e:
        logger.error(f"Failed to fetch newsletter items: {e}")
    return items
