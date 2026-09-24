from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, datetime

from app.utils.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.ingest_feeds.ingest_all_feeds", bind=True, max_retries=3)
def ingest_all_feeds(self) -> dict:
    return asyncio.run(_ingest_all_feeds_async())


async def _ingest_all_feeds_async() -> dict:
    from sqlalchemy import or_, select

    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem
    from app.models.source import Source
    from app.services.ingestion.dispatcher import dispatch_source

    now = datetime.now(UTC)
    rng = random.Random()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Source).where(
                Source.is_active == True,
                or_(Source.next_poll_at.is_(None), Source.next_poll_at <= now),
            )
        )
        sources = list(result.scalars().all())
        logger.info(f"Ingesting {len(sources)} sources")

        total_new = 0
        for source in sources:
            try:
                raw_items = await dispatch_source(source, session)
                # Newsletter content is private to the forwarding user; tag it
                # so it never enters another user's discovery pool (audit 06-6).
                owner_user_id = source.user_id if source.source_type == "newsletter" else None
                for raw in raw_items:
                    item = ContentItem(
                        source_id=source.id,
                        owner_user_id=owner_user_id,
                        url=raw.url,
                        title=raw.title,
                        author=raw.author,
                        published_at=raw.published_at,
                        full_text=raw.full_text,
                        word_count=raw.word_count,
                    )
                    session.add(item)
                    total_new += 1

                from app.services.ingestion.schedule import apply_poll_result

                status = getattr(source, "last_http_status", None)
                moment = datetime.now(UTC)
                failed = status == 429 or (isinstance(status, int) and status >= 500)
                gone = status == 410
                if failed or gone:
                    source.last_error_at = moment
                    source.last_error = f"HTTP {status}"
                apply_poll_result(
                    source,
                    now=moment,
                    rng=rng,
                    new_items=bool(raw_items) and not failed and not gone,
                    error=failed,
                    gone=gone,
                    retry_after=getattr(source, "retry_after", None),
                    gap_seconds=_seconds_since(source.last_fetched_at, moment),
                )
                if not failed and not gone:
                    source.last_fetched_at = moment
                    source.last_error = None
                    source.last_error_at = None
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
                from app.services.ingestion.schedule import apply_poll_result

                apply_poll_result(source, now=datetime.now(UTC), rng=rng, error=True)
                await session.flush()

        await session.commit()
        logger.info(f"Ingested {total_new} new items")
        return {"new_items": total_new, "sources_processed": len(sources)}


def _seconds_since(then: datetime | None, now: datetime) -> int:
    if then is None:
        return 0
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    return max(0, int((now - then).total_seconds()))


@celery_app.task(name="app.workers.tasks.ingest_feeds.ingest_creator_feeds", bind=True)
def ingest_creator_feeds(self) -> dict:
    return asyncio.run(_ingest_creator_feeds_async())


async def _ingest_creator_feeds_async() -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem
    from app.models.creator import Creator
    from app.services.creator.tracker import fetch_creator_content

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Creator))
        creators = list(result.scalars().all())
        total_new = 0

        for creator in creators:
            try:
                raw_items = await fetch_creator_content(creator, session)
                for raw in raw_items:
                    platform_id = (
                        uuid.UUID(raw.creator_platform_id) if raw.creator_platform_id else None
                    )
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
