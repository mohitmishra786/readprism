from __future__ import annotations

import asyncio
import uuid

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
            await svc.summarize(item.id, item.title, item.full_text, session, use_llm=not lazy)
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
            logger.info(f"Semantic duplicate detected for {item.id} — skipping PRS computation")
            await session.commit()
            return {"status": "duplicate", "content_item_id": str(content_item_id)}

        # Ready to rank. Scores are computed live at digest time (#160), so
        # "scored" now means "rankable": the ingest-to-score lag metric
        # measures how long an item waits for its embedding.
        if item.scored_at is None:
            from datetime import UTC, datetime

            item.scored_at = datetime.now(UTC)

        # Index in Meilisearch for full-text search
        from app.utils.search import index_content_item

        await index_content_item(
            item.id,
            {
                "title": item.title,
                "summary_headline": item.summary_headline or "",
                "summary_brief": item.summary_brief or "",
                "author": item.author or "",
                "topic_clusters": item.topic_clusters or [],
                "source_id": str(item.source_id) if item.source_id else None,
                "creator_platform_id": str(item.creator_platform_id)
                if item.creator_platform_id
                else None,
                "url": item.url,
                "published_at": item.published_at.isoformat() if item.published_at else None,
            },
        )

        await session.commit()
        return {"status": "ok", "content_item_id": str(content_item_id)}


@celery_app.task(name="app.workers.tasks.compute_embeddings.summarize_item_with_llm", bind=True)
def summarize_item_with_llm(self, content_item_id: str) -> dict:
    """LLM summary for an item someone opened (#147)."""
    return asyncio.run(_summarize_item_async(uuid.UUID(content_item_id)))


async def _summarize_item_async(content_item_id: uuid.UUID) -> dict:
    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem
    from app.services.summarization.lazy import ensure_llm_summaries

    async with AsyncSessionLocal() as session:
        item = await session.get(ContentItem, content_item_id)
        if item is None:
            return {"status": "not_found"}
        calls = await ensure_llm_summaries([item])
        await session.commit()
        return {"status": "ok", "llm_calls": calls, "summary_source": item.summary_source}
