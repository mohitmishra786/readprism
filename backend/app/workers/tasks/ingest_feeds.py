from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone, timedelta

from app.workers.celery_app import celery_app
from app.utils.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.ingest_feeds.ingest_all_feeds", bind=True, max_retries=3)
def ingest_all_feeds(self) -> dict:
    return asyncio.run(_ingest_all_feeds_async())


async def _ingest_all_feeds_async() -> dict:
    from app.database import AsyncSessionLocal
    from app.models.source import Source
    from app.services.ingestion.dispatcher import dispatch_source
    from app.models.content import ContentItem
    from sqlalchemy import select, or_

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Source).where(
                Source.is_active == True,
                or_(Source.last_fetched_at < cutoff, Source.last_fetched_at.is_(None)),
            )
        )
        sources = list(result.scalars().all())
        logger.info(f"Ingesting {len(sources)} sources")

        total_new = 0
        for source in sources:
            try:
                raw_items = await dispatch_source(source, session)
                for raw in raw_items:
                    item = ContentItem(
                        source_id=source.id,
                        url=raw.url,
                        title=raw.title,
                        author=raw.author,
                        published_at=raw.published_at,
                        full_text=raw.full_text,
                        word_count=raw.word_count,
                    )
                    session.add(item)
                    total_new += 1

                source.last_fetched_at = datetime.now(timezone.utc)
                source.fetch_error_count = 0
                await session.flush()

                # Enqueue embedding computation for each new item
                for raw in raw_items:
                    # Get the saved item ID
                    saved_result = await session.execute(
                        select(ContentItem.id).where(ContentItem.url == raw.url)
                    )
                    item_id = saved_result.scalar_one_or_none()
                    if item_id:
                        from app.workers.tasks.compute_embeddings import compute_embedding_for_item
                        compute_embedding_for_item.delay(str(item_id))

            except Exception as e:
                logger.error(f"Failed to ingest source {source.id}: {e}")
                source.fetch_error_count = (source.fetch_error_count or 0) + 1
                await session.flush()

        await session.commit()
        logger.info(f"Ingested {total_new} new items")
        return {"new_items": total_new, "sources_processed": len(sources)}


@celery_app.task(name="app.workers.tasks.ingest_feeds.ingest_creator_feeds", bind=True)
def ingest_creator_feeds(self) -> dict:
    return asyncio.run(_ingest_creator_feeds_async())


async def _ingest_creator_feeds_async() -> dict:
    from app.database import AsyncSessionLocal
    from app.models.creator import Creator, CreatorPlatform
    from app.models.content import ContentItem
    from app.services.creator.tracker import fetch_creator_content
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Creator))
        creators = list(result.scalars().all())
        total_new = 0

        for creator in creators:
            try:
                raw_items = await fetch_creator_content(creator, session)
                for raw in raw_items:
                    platform_id = uuid.UUID(raw.creator_platform_id) if raw.creator_platform_id else None
                    item = ContentItem(
                        creator_platform_id=platform_id,
                        url=raw.url,
                        title=raw.title,
                        author=raw.author,
                        published_at=raw.published_at,
                        full_text=raw.full_text,
                        word_count=raw.word_count,
                    )
                    session.add(item)
                    total_new += 1
                await session.flush()

                for raw in raw_items:
                    saved_result = await session.execute(
                        select(ContentItem.id).where(ContentItem.url == raw.url)
                    )
                    item_id = saved_result.scalar_one_or_none()
                    if item_id:
                        from app.workers.tasks.compute_embeddings import compute_embedding_for_item
                        compute_embedding_for_item.delay(str(item_id))
            except Exception as e:
                logger.error(f"Failed to ingest creator {creator.id}: {e}")

        await session.commit()
        return {"new_items": total_new, "creators_processed": len(creators)}
