"""Provider-agnostic LLM client: retired models, rate limits, and extractive fallback."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.config import get_settings
from app.services.llm.client import LLMClient, TokenBucket
from app.services.summarization.extractive import extractive_summary
from app.services.summarization.groq_client import GroqSummarizer
from app.services.summarization.summarizer import SummarizationService

MOCK_JSON = json.dumps(
    {
        "headline": "Test article headline",
        "brief": "This is a two sentence brief. It covers the main point.",
        "detailed": "A detailed paragraph for a sophisticated reader.",
        "depth_score": 0.75,
        "is_original_reporting": True,
        "has_citations": True,
        "topic_clusters": ["machine learning"],
        "reading_time_minutes": 7,
    }
)


async def _no_sleep(_: float) -> None:
    return None


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    async def sleep(self, delay: float) -> None:
        self.t += delay


def _client(handler, **kwargs) -> LLMClient:
    return LLMClient(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
        tpm=100_000,
        rpm=1_000,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_summarizer_sends_configured_model_not_a_literal():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["model"] = json.loads(request.content)["model"]
        return httpx.Response(200, json={"choices": [{"message": {"content": MOCK_JSON}}]})

    result = await GroqSummarizer(llm=_client(handler)).summarize("Title", "Body text here.")
    assert result is not None
    assert result.summary_source == "llm"
    assert result.headline == "Test article headline"
    assert seen["model"] == get_settings().llm_model_primary
    assert "llama" not in seen["model"]


@pytest.mark.asyncio
async def test_model_not_found_opens_circuit_and_stops():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, json={"error": {"message": "model not found"}})

    client = _client(handler)
    assert (
        await client.complete(model="missing-model", messages=[{"role": "user", "content": "hi"}])
        is None
    )
    assert client.circuit_open
    assert (
        await client.complete(model="missing-model", messages=[{"role": "user", "content": "hi"}])
        is None
    )
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_429_retries_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, json={"error": "slow down"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    text = await _client(handler).complete(
        model="any-model", messages=[{"role": "user", "content": "hi"}]
    )
    assert text == "ok"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_timeout_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    assert (
        await _client(handler).complete(
            model="any-model", messages=[{"role": "user", "content": "hi"}]
        )
        is None
    )


@pytest.mark.asyncio
async def test_token_bucket_waits_until_the_window_refills():
    clock = _Clock()
    bucket = TokenBucket(tpm=60, rpm=60, clock=clock, sleep=clock.sleep)
    await bucket.acquire(60)
    await bucket.acquire(30)
    # 30 tokens at 1 token/second (60 per minute) needs about 30 seconds.
    assert clock.t >= 29


@pytest.mark.asyncio
async def test_token_bucket_accepts_a_request_larger_than_the_bucket():
    clock = _Clock()
    bucket = TokenBucket(tpm=60, rpm=60, clock=clock, sleep=clock.sleep)
    await bucket.acquire(61)
    assert clock.t < 5


def test_extractive_summary_without_a_model():
    result = extractive_summary(
        "Rust async runtimes",
        "Tokio schedules tasks. The runtime is cooperative. Readers should know the tradeoffs.",
    )
    assert result.summary_source == "extractive"
    assert "Tokio" in result.brief
    assert result.reading_time_minutes >= 1


@pytest.mark.asyncio
async def test_digest_summary_ships_with_llm_unset(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "groq_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")

    session = AsyncMock()
    empty = MagicMock()
    empty.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=empty)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.summarization.summarizer.cache_get", AsyncMock(return_value=None))
        mp.setattr("app.services.summarization.summarizer.cache_set", AsyncMock())
        result = await SummarizationService().summarize(
            __import__("uuid").uuid4(),
            "A title about compilers",
            "Parsers turn text into trees. Optimizers rewrite those trees. The article explains both.",
            session,
        )
    assert result is not None
    assert result.summary_source == "extractive"
    assert result.brief
