from __future__ import annotations

import uuid
from typing import Optional

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.source import Source
from app.services.ingestion.rss_parser import RawContentItem, parse_feed
from app.services.ingestion.scraper import scrape_page
from app.utils.cache import get_redis
from app.utils.logging import get_logger

logger = get_logger(__name__)

SEMANTIC_DEDUP_THRESHOLD = 0.92  # cosine similarity above which items are considered duplicates


async def dispatch_source(source: Source, session: AsyncSession) -> list[RawContentItem]:
    raw_items: list[RawContentItem] = []

    if source.source_type == "newsletter":
        raw_items = await _fetch_newsletter_items(source, session)
    elif source.feed_url or source.source_type == "rss":
        feed_url = source.feed_url or source.url
        raw_items = await parse_feed(feed_url)
        if not raw_items and source.feed_url is None:
            # Try autodiscovery
            from app.services.ingestion.rss_parser import _autodiscover_feed
            discovered = await _autodiscover_feed(source.url)
            if discovered:
                raw_items = await parse_feed(discovered)
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

    existing_urls_result = await session.execute(
        select(ContentItem.url).where(
            ContentItem.url.in_([item.url for item in raw_items])
        )
    )
    existing_urls = set(row[0] for row in existing_urls_result.fetchall())
    new_items = [item for item in raw_items if item.url not in existing_urls]

    logger.info(f"Source {source.id}: {len(raw_items)} fetched, {len(new_items)} new after URL dedup")
    return new_items


async def semantic_dedup(
    item_id: uuid.UUID,
    embedding: list[float],
    session: AsyncSession,
    window_hours: int = 72,
) -> bool:
    """Return True if a semantically similar item already exists in the recent queue."""
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    try:
        result = await session.execute(
            text("""
                SELECT id, embedding <=> CAST(:emb AS vector) AS dist
                FROM content_items
                WHERE fetched_at >= :cutoff
                  AND id != :item_id
                  AND embedding IS NOT NULL
                ORDER BY dist ASC
                LIMIT 1
            """),
            {
                "emb": str(embedding),
                "cutoff": cutoff,
                "item_id": str(item_id),
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
                items.append(RawContentItem(
                    url=f"newsletter://{source.user_id}/{msg_id}",
                    title=data.get("subject", "Newsletter"),
                    author=data.get("sender"),
                    full_text=data.get("body"),
                    word_count=len(data.get("body", "").split()) if data.get("body") else None,
                ))
    except Exception as e:
        logger.error(f"Failed to fetch newsletter items: {e}")
    return items
