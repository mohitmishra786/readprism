from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.creator import Creator, CreatorPlatform
from app.services.ingestion.rss_parser import RawContentItem, parse_feed
from app.services.ingestion.scraper import scrape_page
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def fetch_creator_content(
    creator: Creator, session: AsyncSession
) -> list[RawContentItem]:
    # Load platforms
    result = await session.execute(
        select(CreatorPlatform).where(CreatorPlatform.creator_id == creator.id)
    )
    platforms = list(result.scalars().all())

    all_items: list[RawContentItem] = []
    seen_urls: set[str] = set()

    for platform in platforms:
        items: list[RawContentItem] = []

        if platform.feed_url:
            items = await parse_feed(platform.feed_url)
        elif platform.platform_url:
            # Try to scrape profile for new content indicators
            item = await scrape_page(platform.platform_url)
            if item:
                items = [item]

        for item in items:
            # Tag with creator platform
            item.creator_platform_id = str(platform.id)
            # Deduplicate across platforms
            if item.url not in seen_urls:
                seen_urls.add(item.url)
                all_items.append(item)

        # Update last_fetched_at
        from datetime import datetime, timezone
        platform.last_fetched_at = datetime.now(timezone.utc)

    await session.flush()
    logger.info(f"Fetched {len(all_items)} items for creator {creator.id}")
    return all_items
