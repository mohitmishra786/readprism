from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from app.utils.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="app.workers.tasks.compute_embeddings.compute_embedding_for_item", bind=True, max_retries=3
)
def compute_embedding_for_item(self, content_item_id: str) -> dict:
    return asyncio.run(_compute_embedding_async(uuid.UUID(content_item_id)))


async def _compute_embedding_async(content_item_id: uuid.UUID) -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem
    from app.services.summarization.summarizer import SummarizationService
    from app.utils.embeddings import get_embedding_service

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ContentItem).where(ContentItem.id == content_item_id))
        item = result.scalar_one_or_none()
        if item is None:
            logger.warning(f"ContentItem {content_item_id} not found")
            return {"status": "not_found"}

        # Summarize if not yet cached. Lazy mode (default, #147) writes the
        # extractive summary here and leaves the model for items that reach a
        # digest or the reader.
        from app.config import get_settings

        lazy = get_settings().llm_summarize != "all"
        if item.full_text and (
            item.summary_source is None or (not lazy and not item.summarization_cached)
        ):
            svc = SummarizationService()
            await svc.summarize(
                item.id,
                item.title,
                item.full_text,
                session,
                use_llm=not lazy,
                language=item.language,
                is_transcript=bool(item.transcript_url),
            )
            await session.refresh(item)

        # Embed
        embedding_svc = get_embedding_service()
        from app.services.embeddings.registry import MINILM_DIM, VERSION
        from app.services.embeddings.text import embedding_pieces, pool_vectors

        pieces = embedding_pieces(
            title=item.title or "",
            lead=item.summary_brief or "",
            body=item.full_text or "",
        )
        if not pieces:
            await session.commit()
            return {"status": "empty", "content_item_id": str(content_item_id)}
        encoded = await embedding_svc.encode_batch_cached(pieces)
        if any(len(vector) != MINILM_DIM for vector in encoded):
            logger.error(
                "Refusing embedding for %s: model %s did not return %s dimensions",
                content_item_id,
                embedding_svc.model_name,
                MINILM_DIM,
            )
            await session.commit()
            return {"status": "dimension_mismatch", "content_item_id": str(content_item_id)}
        embedding = pool_vectors(encoded)
        item.embedding = embedding
        item.embedding_model = embedding_svc.model_name
        item.embedding_dim = len(embedding)
        item.embedding_version = VERSION
        await session.flush()

        # Semantic deduplication: mark item inactive if near-duplicate exists
        from app.services.ingestion.dispatcher import semantic_dedup

        is_dup = await semantic_dedup(item.id, embedding, session, owner_user_id=item.owner_user_id)
        if is_dup:
            logger.info(f"Semantic duplicate detected for {item.id}: skipping PRS computation")
            await session.commit()
            return {"status": "duplicate", "content_item_id": str(content_item_id)}

        # Ready to rank. Scores are computed live at digest time (#160), so
        # "scored" now means "rankable": the ingest-to-score lag metric
        # measures how long an item waits for its embedding.
        if item.scored_at is None:
            from datetime import UTC, datetime

            item.scored_at = datetime.now(UTC)

        await session.commit()
        return {"status": "ok", "content_item_id": str(content_item_id)}


@celery_app.task(name="app.workers.tasks.compute_embeddings.summarize_item_with_llm", bind=True)
def summarize_item_with_llm(self, content_item_id: str, user_id: str | None = None) -> dict:
    """LLM summary for an item someone opened (#147); on their own key if given (#255)."""
    return asyncio.run(
        _summarize_item_async(uuid.UUID(content_item_id), uuid.UUID(user_id) if user_id else None)
    )


async def _summarize_item_async(
    content_item_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> dict:
    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem
    from app.services.llm.user_keys import summarizer_for
    from app.services.summarization.lazy import ensure_llm_summaries

    async with AsyncSessionLocal() as session:
        item = await session.get(ContentItem, content_item_id)
        if item is None:
            return {"status": "not_found"}
        own = await summarizer_for(session, user_id) if user_id else None
        calls = await ensure_llm_summaries([item], summarizer=own)
        await session.commit()
        return {"status": "ok", "llm_calls": calls, "summary_source": item.summary_source}


# Items committed by ingestion whose embedding task never reached the broker
# (or was lost) would otherwise stay unembedded forever: later polls skip
# their URL. Re-enqueue them, at most once per item per REPAIR_RETRY.
REPAIR_MIN_AGE = timedelta(minutes=15)
REPAIR_WINDOW = timedelta(days=3)
REPAIR_RETRY_SECONDS = 6 * 3600
REPAIR_BATCH = 500


@celery_app.task(name="app.workers.tasks.compute_embeddings.repair_missing_embeddings")
def repair_missing_embeddings() -> dict:
    return asyncio.run(_repair_missing_embeddings_async())


async def _repair_missing_embeddings_async(now: datetime | None = None) -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem
    from app.utils.cache import cache_set_nx

    now = now or datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        ids = [
            row[0]
            for row in (
                await session.execute(
                    select(ContentItem.id)
                    .where(
                        ContentItem.embedding.is_(None),
                        ContentItem.rankable.is_(True),
                        ContentItem.fetched_at >= now - REPAIR_WINDOW,
                        ContentItem.fetched_at <= now - REPAIR_MIN_AGE,
                    )
                    .order_by(ContentItem.fetched_at.desc())
                    .limit(REPAIR_BATCH)
                )
            ).all()
        ]
    queued = 0
    for item_id in ids:
        if not await cache_set_nx(f"embed-repair:{item_id}", 1, ttl_seconds=REPAIR_RETRY_SECONDS):
            continue
        try:
            compute_embedding_for_item.delay(str(item_id))
            queued += 1
        except Exception as e:
            logger.warning(f"Embedding repair could not enqueue {item_id}: {e}")
    if queued:
        logger.info(f"Embedding repair re-queued {queued} items")
    return {"missing": len(ids), "queued": queued}


@celery_app.task(
    name="app.workers.tasks.compute_embeddings.reembed_outdated_items",
    bind=True,
    max_retries=3,
)
def reembed_outdated_items(
    self,
    batch_size: int | None = None,
    max_batches: int | None = None,
) -> dict:
    """Online re-embed task (embed queue): re-encodes rows whose embedding_model != active (#244)."""
    return asyncio.run(
        _reembed_outdated_items_async(batch_size=batch_size, max_batches=max_batches)
    )


async def _reembed_outdated_items_async(
    batch_size: int | None = None,
    max_batches: int | None = None,
) -> dict:
    from app.config import get_settings
    from app.database import AsyncSessionLocal
    from app.services.embeddings.reembed import (
        get_reembed_cursor,
        reembed_batch,
        reembed_interest_batch,
    )
    from app.services.embeddings.registry import active_spec
    from app.utils.embeddings import get_embedding_service

    settings = get_settings()
    batch_size = batch_size or settings.embedding_reembed_batch
    pause = settings.embedding_reembed_pause_seconds
    active = active_spec(
        model=settings.embedding_model,
        cutover=settings.embedding_cutover_enabled,
    )
    encoder = get_embedding_service()

    total_reembedded = 0
    batches_run = 0
    cursor = await get_reembed_cursor()

    while True:
        async with AsyncSessionLocal() as session:
            result = await reembed_batch(
                session=session,
                active=active,
                batch_size=batch_size,
                cursor=cursor,
                encoder=encoder,
            )
        total_reembedded += result["reembedded"]
        cursor = result["next_cursor"]
        batches_run += 1

        if result["done"]:
            break
        if max_batches is not None and batches_run >= max_batches:
            break
        if pause > 0:
            await asyncio.sleep(pause)

    # Interest topics follow the items: ranking compares the two (#244).
    topics_reembedded = 0
    topics_done = False
    while result["done"] and not (max_batches is not None and batches_run >= max_batches):
        async with AsyncSessionLocal() as session:
            topic_result = await reembed_interest_batch(
                session=session, active=active, batch_size=batch_size, encoder=encoder
            )
        topics_reembedded += topic_result["reembedded"]
        batches_run += 1
        if topic_result["done"]:
            topics_done = True
            break
        if pause > 0:
            await asyncio.sleep(pause)

    logger.info(
        "Re-embed progress: active=%s, batches=%d, re-embedded=%d, done=%s",
        active.name,
        batches_run,
        total_reembedded,
        result["done"],
    )
    return {
        "status": "ok",
        "batches_run": batches_run,
        "total_reembedded": total_reembedded,
        "topics_reembedded": topics_reembedded,
        "cursor": cursor,
        "done": result["done"] and topics_done,
        "active_model": active.name,
    }
