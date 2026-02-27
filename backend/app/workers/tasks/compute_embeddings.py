from __future__ import annotations

import asyncio
import uuid

from app.workers.celery_app import celery_app
from app.utils.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.compute_embeddings.compute_embedding_for_item", bind=True, max_retries=3)
def compute_embedding_for_item(self, content_item_id: str) -> dict:
    return asyncio.run(_compute_embedding_async(uuid.UUID(content_item_id)))


async def _compute_embedding_async(content_item_id: uuid.UUID) -> dict:
    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem
    from app.models.source import Source
    from app.services.summarization.summarizer import SummarizationService
    from app.utils.embeddings import get_embedding_service, EmbeddingService
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ContentItem).where(ContentItem.id == content_item_id))
        item = result.scalar_one_or_none()
        if item is None:
            logger.warning(f"ContentItem {content_item_id} not found")
            return {"status": "not_found"}

        # Summarize if not yet cached
        if not item.summarization_cached and item.full_text:
            svc = SummarizationService()
            await svc.summarize(item.id, item.title, item.full_text, session)
            await session.refresh(item)

        # Embed
        embedding_svc = get_embedding_service()
        embed_text = EmbeddingService.build_embedding_text(
            title=item.title,
            summary_brief=item.summary_brief,
        )
        embedding = await embedding_svc.encode_single(embed_text)
        item.embedding = embedding
        await session.flush()

        # Semantic deduplication: mark item inactive if near-duplicate exists
        from app.services.ingestion.dispatcher import semantic_dedup
        is_dup = await semantic_dedup(item.id, embedding, session)
        if is_dup:
            logger.info(f"Semantic duplicate detected for {item.id} — skipping PRS computation")
            await session.commit()
            return {"status": "duplicate", "content_item_id": str(content_item_id)}

        # Enqueue PRS computation for all users following this source
        if item.source_id:
            from app.models.user import User
            users_result = await session.execute(
                select(User.id)
                .join(Source, Source.user_id == User.id)
                .where(Source.id == item.source_id)
            )
            user_ids = [row[0] for row in users_result.fetchall()]
            for uid in user_ids:
                from app.workers.tasks.compute_prs import compute_prs_for_user_item
                compute_prs_for_user_item.delay(str(uid), str(content_item_id))

        # Index in Meilisearch for full-text search
        from app.utils.search import index_content_item
        await index_content_item(item.id, {
            "title": item.title,
            "summary_headline": item.summary_headline or "",
            "summary_brief": item.summary_brief or "",
            "author": item.author or "",
            "topic_clusters": item.topic_clusters or [],
            "source_id": str(item.source_id) if item.source_id else None,
            "creator_platform_id": str(item.creator_platform_id) if item.creator_platform_id else None,
            "url": item.url,
            "published_at": item.published_at.isoformat() if item.published_at else None,
        })

        await session.commit()
        return {"status": "ok", "content_item_id": str(content_item_id)}
