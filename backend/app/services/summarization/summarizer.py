from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.content import ContentItem
from app.services.summarization.groq_client import GroqSummarizer, SummarizationResult
from app.utils.cache import cache_get, cache_set
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_groq_summarizer: Optional[GroqSummarizer] = None


def get_groq_summarizer() -> GroqSummarizer:
    global _groq_summarizer
    if _groq_summarizer is None:
        _groq_summarizer = GroqSummarizer()
    return _groq_summarizer


class SummarizationService:
    async def summarize(
        self, content_item_id: uuid.UUID, title: str, full_text: str, session: AsyncSession
    ) -> Optional[SummarizationResult]:
        cache_key = f"summary:{content_item_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for summary:{content_item_id}")
            return SummarizationResult(**cached)

        # Primary: Groq
        result = await get_groq_summarizer().summarize(title, full_text)

        # Fallback: OpenAI (only if enabled)
        if result is None and settings.openai_fallback_enabled:
            logger.info(f"Groq failed, falling back to OpenAI for {content_item_id}")
            from app.services.summarization.openai_client import OpenAISummarizer
            result = await OpenAISummarizer().summarize(title, full_text)

        if result is not None:
            # Cache the result
            await cache_set(cache_key, {
                "headline": result.headline,
                "brief": result.brief,
                "detailed": result.detailed,
                "depth_score": result.depth_score,
                "is_original_reporting": result.is_original_reporting,
                "has_citations": result.has_citations,
                "topic_clusters": result.topic_clusters,
                "reading_time_minutes": result.reading_time_minutes,
            }, ttl_seconds=30 * 24 * 3600)

            # Update DB
            stmt = select(ContentItem).where(ContentItem.id == content_item_id)
            row = await session.execute(stmt)
            item = row.scalar_one_or_none()
            if item:
                item.summary_headline = result.headline
                item.summary_brief = result.brief
                item.summary_detailed = result.detailed
                item.content_depth_score = result.depth_score
                item.is_original_reporting = result.is_original_reporting
                item.has_citations = result.has_citations
                item.topic_clusters = result.topic_clusters
                item.reading_time_minutes = result.reading_time_minutes
                item.summarization_cached = True
                await session.flush()

        return result
