from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.content import ContentItem
from app.services.llm.client import PROMPT_VERSION
from app.services.summarization.extractive import extractive_summary
from app.services.summarization.groq_client import LLMSummarizer, SummarizationResult
from app.utils.cache import cache_get, cache_set
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_llm_summarizer: LLMSummarizer | None = None


def get_llm_summarizer() -> LLMSummarizer:
    global _llm_summarizer
    if _llm_summarizer is None:
        _llm_summarizer = LLMSummarizer()
    return _llm_summarizer


# Deprecated alias (issue #265): the historical Groq name, removed in v0.3.
get_groq_summarizer = get_llm_summarizer


class SummarizationService:
    async def summarize(
        self,
        content_item_id: uuid.UUID,
        title: str,
        full_text: str,
        session: AsyncSession,
        *,
        use_llm: bool = True,
        language: str | None = None,
        is_transcript: bool = False,
    ) -> SummarizationResult | None:
        """Summarize and store. `use_llm=False` writes the extractive summary
        without calling the model (lazy mode, #147)."""
        if not use_llm:
            result = extractive_summary(title, full_text)
            await self._store(content_item_id, result, session)
            return result
        model_tag = settings.llm_model_primary if settings.llm_configured else "extractive"
        cache_key = f"summary:{content_item_id}:{PROMPT_VERSION}:{model_tag}"
        cached = await cache_get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for summary:{content_item_id}")
            return SummarizationResult(**cached)

        # LLM when configured. A miss, a 404, or a rate limit must not block the digest.
        llm_result = await get_llm_summarizer().summarize(
            title, full_text, language=language, is_transcript=is_transcript
        )
        if llm_result is None:
            logger.info("extractive summary for item %s (llm unavailable)", content_item_id)
            result = extractive_summary(title, full_text)
        else:
            result = llm_result

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

            await self._store(content_item_id, result, session)

        return result

    async def _store(
        self, content_item_id: uuid.UUID, result: SummarizationResult, session: AsyncSession
    ) -> None:
        item = (
            await session.execute(select(ContentItem).where(ContentItem.id == content_item_id))
        ).scalar_one_or_none()
        if item is not None:
            apply_summary(item, result)
            await session.flush()


def apply_summary(item: ContentItem, result: SummarizationResult) -> None:
    item.summary_headline = result.headline
    item.summary_brief = result.brief
    item.summary_detailed = result.detailed
    item.content_depth_score = result.depth_score
    item.is_original_reporting = result.is_original_reporting
    item.has_citations = result.has_citations
    # Keep extractive keyword topics when the model returned none.
    if result.topic_clusters or not item.topic_clusters:
        item.topic_clusters = result.topic_clusters
    item.reading_time_minutes = result.reading_time_minutes
    item.summary_source = result.summary_source
    # The embedding worker retries while this is false. Only an LLM summary
    # should suppress that retry.
    item.summarization_cached = result.summary_source == "llm"
