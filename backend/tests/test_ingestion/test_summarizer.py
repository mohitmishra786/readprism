from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.summarization.groq_client import GroqSummarizer, SummarizationResult

MOCK_GROQ_RESPONSE = json.dumps(
    {
        "headline": "Test article headline",
        "brief": "This is a two sentence brief. It covers the main point.",
        "detailed": "This is a detailed paragraph covering the key takeaways for a sophisticated reader.",
        "depth_score": 0.75,
        "is_original_reporting": True,
        "has_citations": True,
        "topic_clusters": ["machine learning", "neural networks"],
        "reading_time_minutes": 7,
    }
)


@pytest.mark.asyncio
async def test_groq_summarizer_calls_correct_model():
    """Summarizer should call the configured primary model."""
    import httpx

    from app.config import get_settings
    from app.services.llm.client import LLMClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": MOCK_GROQ_RESPONSE}}]})

    async def _no_sleep(_: float) -> None:
        return None

    summarizer = GroqSummarizer(
        llm=LLMClient(
            api_key="test-key",
            transport=httpx.MockTransport(handler),
            sleep=_no_sleep,
            tpm=100_000,
            rpm=1_000,
        )
    )
    result = await summarizer.summarize("Test Title", "Full text of the article...")

    assert result is not None
    assert isinstance(result, SummarizationResult)
    assert result.headline == "Test article headline"
    assert result.depth_score == 0.75
    assert "machine learning" in result.topic_clusters
    assert result.summary_source == "llm"
    assert get_settings().llm_model_primary


@pytest.mark.asyncio
async def test_summarization_service_caches_result():
    """SummarizationService should cache results and not call LLM twice."""
    from app.services.summarization.summarizer import SummarizationService

    content_id = uuid.uuid4()
    cached_data = {
        "headline": "Cached headline",
        "brief": "Cached brief.",
        "detailed": "Cached detailed.",
        "depth_score": 0.6,
        "is_original_reporting": False,
        "has_citations": False,
        "topic_clusters": ["cached topic"],
        "reading_time_minutes": 5,
    }

    with patch("app.services.summarization.summarizer.cache_get", return_value=cached_data):
        svc = SummarizationService()
        result = await svc.summarize(content_id, "Title", "Full text", AsyncMock())

    assert result is not None
    assert result.headline == "Cached headline"
