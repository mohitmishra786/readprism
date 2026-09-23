from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.content import ContentItem
from app.services.llm.client import PROMPT_VERSION
from app.services.summarization.extractive import extractive_summary
from app.services.summarization.groq_client import GroqSummarizer, SummarizationResult
from app.utils.cache import cache_get, cache_set
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_groq_summarizer: GroqSummarizer | None = None


def get_groq_summarizer() -> GroqSummarizer:
    global _groq_summarizer
    if _groq_summarizer is None:
        _groq_summarizer = GroqSummarizer()
    return _groq_summarizer


class SummarizationService:
    async def summarize(
        self, content_item_id: uuid.UUID, title: str, full_text: str, session: AsyncSession
    ) -> SummarizationResult | None:
        model_tag = settings.llm_model_primary if settings.llm_configured else "extractive"
        cache_key = f"summary:{content_item_id}:{PROMPT_VERSION}:{model_tag}"
        cached = await cache_get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for summary:{content_item_id}")
            return SummarizationResult(**cached)

        # LLM when configured. A miss, a 404, or a rate limit must not block the digest.
        result = await get_groq_summarizer().summarize(title, full_text)
        if result is None:
            logger.info("extractive summary for item %s (llm unavailable)", content_item_id)
            result = extractive_summary(title, full_text)

        if result is not None:
            # An extractive stand-in must not occupy the LLM cache for 30 days,
            # or a recovered provider is never asked again.
            ttl = (
                30 * 24 * 3600
                if result.summary_source == "llm" or not settings.llm_configured
                else 3600
            )
            await cache_set(
                cache_key,
                {
                    "headline": result.headline,
                    "brief": result.brief,
                    "detailed": result.detailed,
                    "depth_score": result.depth_score,
                    "is_original_reporting": result.is_original_reporting,
                    "has_citations": result.has_citations,
                    "topic_clusters": result.topic_clusters,
                    "reading_time_minutes": result.reading_time_minutes,
                    "summary_source": result.summary_source,
                },
                ttl_seconds=ttl,
            )

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
                item.summary_source = result.summary_source
                # The embedding worker retries while this is false. Only an LLM
                # summary should suppress that retry.
                item.summarization_cached = result.summary_source == "llm"
                await session.flush()

        return result
