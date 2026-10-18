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


async def _insert_items(session, rows: list[dict]) -> list[uuid.UUID]:
    """Insert content rows, skipping any that already exist; return new ids.

    `content_items` has unique constraints (URL, and source+guid). Another
    user's subscription, an extension save, an import, or an aggregator that
    links the same article can all have stored the URL already. A plain
    INSERT would raise on flush and abort the whole transaction, so conflicts
    are skipped in the database instead (#100).
    """
    from sqlalchemy.dialects.postgresql import insert

    from app.models.content import ContentItem

    new_ids: list[uuid.UUID] = []
    for row in rows:
        result = await session.execute(
            insert(ContentItem).values(**row).on_conflict_do_nothing().returning(ContentItem.id)
        )
        new_id = result.scalar_one_or_none()
        if new_id is not None:
            new_ids.append(new_id)
    return new_ids


def _enqueue_embeddings(item_ids: list[uuid.UUID]) -> None:
    from app.workers.tasks.compute_embeddings import compute_embedding_for_item

    for item_id in item_ids:
        compute_embedding_for_item.delay(str(item_id))


@celery_app.task(name="app.workers.tasks.ingest_feeds.ingest_user_sources", bind=True)
def ingest_user_sources(self, user_id: str) -> dict:
    """Fetch one user's sources now, regardless of schedule (first digest, #102)."""
    return asyncio.run(_ingest_all_feeds_async(user_id=uuid.UUID(user_id)))


async def _ingest_all_feeds_async(user_id: uuid.UUID | None = None) -> dict:
    """Ingest due sources, or every active source of `user_id` when given."""
    from sqlalchemy import or_, select

    from app.database import AsyncSessionLocal
    from app.models.source import Source

    now = datetime.now(UTC)
    rng = random.Random()

    async with AsyncSessionLocal() as session:
        query = select(Source.id).where(Source.is_active == True)
        if user_id is not None:
            query = query.where(Source.user_id == user_id)
        else:
            query = query.where(or_(Source.next_poll_at.is_(None), Source.next_poll_at <= now))
        result = await session.execute(query)
        source_ids = [row[0] for row in result.all()]
    logger.info(f"Ingesting {len(source_ids)} sources")

    # One session and one commit per source: a failure in one source (bad feed,
    # constraint violation, extraction crash) can never discard another
    # source's items or its poll-schedule update (#100).
    total_new = 0
    for source_id in source_ids:
        new_ids: list[uuid.UUID] = []
        async with AsyncSessionLocal() as session:
            try:
                source = await session.get(Source, source_id)
                if source is None:
                    continue
                new_ids = await _ingest_source(source, session, rng)
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to ingest source {source_id}: {e}")
                await _record_source_failure(source_id, rng, str(e))
                continue
        total_new += len(new_ids)
        _enqueue_embeddings(new_ids)

    logger.info(f"Ingested {total_new} new items")
    return {"new_items": total_new, "sources_processed": len(source_ids)}


async def _ingest_source(source, session, rng: random.Random) -> list[uuid.UUID]:
    """Fetch one source, store its new items, and update its poll schedule."""
    from app.services.ingestion.dispatcher import dispatch_source
    from app.services.ingestion.schedule import apply_poll_result

    raw_items = await dispatch_source(source, session)
    # Newsletter content is private to the forwarding user; tag it so it never
    # enters another user's discovery pool (audit 06-6).
    owner_user_id = source.user_id if source.source_type == "newsletter" else None
    rows: list[dict] = []
    for raw in raw_items:
        row = {
            "source_id": source.id,
            "owner_user_id": owner_user_id,
            "url": raw.url,
            "title": raw.title,
            "author": raw.author,
            "published_at": raw.published_at,
            "full_text": raw.full_text,
            "word_count": raw.word_count,
            "transcript_url": raw.transcript_url,
            "guid": raw.guid,
            "simhash": raw.simhash,
            "extraction_method": raw.extraction_method,
            "extraction_confidence": raw.extraction_confidence,
            "page_type": raw.page_type,
            "language": raw.language,
            "lead_image_url": raw.lead_image_url,
            "paywalled": raw.paywalled,
            "rankable": raw.rankable,
            "origin": raw.origin or "followed",
            "reading_time_minutes": raw.reading_time_minutes,
        }
        # EC-08: podcast episodes rank on their transcript when the feed
        # carries a Podcast 2.0 transcript link — even when feed text exists
        # (the transcript is richer).
        if raw.transcript_url:
            from app.services.ingestion.transcripts import fetch_transcript_text

            transcript = await fetch_transcript_text(raw.transcript_url)
            if transcript:
                combined = transcript
                if row["full_text"]:
                    combined = f"{transcript}\n\n{row['full_text']}"
                row["full_text"] = combined[:100_000]
                # Metadata from the STORED text (post-truncation).
                row["word_count"] = len(row["full_text"].split())
                row["reading_time_minutes"] = max(1, round(row["word_count"] / 200))
        rows.append(row)

    new_ids = await _insert_items(session, rows)

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
        new_items=bool(new_ids) and not failed and not gone,
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
    return new_ids


async def _record_source_failure(source_id, rng: random.Random, error: str) -> None:
    """Persist backoff for a source whose ingest raised, in a fresh session.

    Without this the source keeps `next_poll_at` unchanged and fails again on
    every beat tick.
    """
    from app.database import AsyncSessionLocal
    from app.models.source import Source
    from app.services.ingestion.schedule import apply_poll_result

    try:
        async with AsyncSessionLocal() as session:
            source = await session.get(Source, source_id)
            if source is None:
                return
            moment = datetime.now(UTC)
            source.last_error_at = moment
            source.last_error = error[:500]
            apply_poll_result(source, now=moment, rng=rng, error=True)
            await session.commit()
    except Exception as e:  # never let bookkeeping take down the run
        logger.error(f"Could not record failure for source {source_id}: {e}")


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
    from app.models.creator import Creator
    from app.services.creator.tracker import fetch_creator_content

    async with AsyncSessionLocal() as session:
        creator_ids = [row[0] for row in (await session.execute(select(Creator.id))).all()]

    # Same isolation as feed ingest (#100): the tracker only dedups within one
    # fetch, so every hourly run re-sees the previous items. They are skipped
    # by ON CONFLICT instead of aborting the run.
    total_new = 0
    for creator_id in creator_ids:
        new_ids: list[uuid.UUID] = []
        async with AsyncSessionLocal() as session:
            try:
                creator = await session.get(Creator, creator_id)
                if creator is None:
                    continue
                raw_items = await fetch_creator_content(creator, session)
                rows = [
                    {
                        "creator_platform_id": (
                            uuid.UUID(raw.creator_platform_id) if raw.creator_platform_id else None
                        ),
                        "url": raw.url,
                        "title": raw.title,
                        "author": raw.author,
                        "published_at": raw.published_at,
                        "full_text": raw.full_text,
                        "word_count": raw.word_count,
                    }
                    for raw in raw_items
                ]
                new_ids = await _insert_items(session, rows)
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to ingest creator {creator_id}: {e}")
                continue
        total_new += len(new_ids)
        _enqueue_embeddings(new_ids)

    return {"new_items": total_new, "creators_processed": len(creator_ids)}
