"""Prometheus exposition at GET /metrics (#170)."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
import pytest

from app.config import get_settings
from app.models.content import ContentItem
from app.services.metrics import prometheus


@pytest.fixture
def token(monkeypatch):
    from app.api import metrics

    monkeypatch.setattr(metrics.settings, "metrics_token", "prom-token")
    return "prom-token"


@pytest.mark.asyncio
async def test_requires_the_metrics_token(client, token):
    assert (await client.get("/metrics")).status_code == 401
    ok = await client.get("/metrics", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("text/plain")
    also = await client.get("/metrics", headers={"X-Metrics-Token": token})
    assert also.status_code == 200


@pytest.mark.asyncio
async def test_exposes_the_listed_series(client, db_session, token):
    db_session.add(
        ContentItem(
            url=f"https://p.example/{uuid.uuid4().hex}",
            title="Fresh",
            fetched_at=datetime.now(UTC) - timedelta(minutes=5),
        )
    )
    await db_session.commit()
    await client.get("/health")
    from app.workers import queue_metrics

    queue_metrics.record("lag", "digest", 4.0)
    queue_metrics.record("run", "app.workers.tasks.build_digest.build_digest_task", 2.0)
    body = (await client.get("/metrics", headers={"X-Metrics-Token": token})).text
    for series in (
        'readprism_http_requests_total{method="GET",route="/health",status="2xx"}',
        "readprism_http_request_duration_seconds_bucket",
        'readprism_queue_wait_seconds{quantile="95",queue="digest"}',
        'readprism_task_runtime_seconds{quantile="50",task="app.workers.tasks.build_digest.build_digest_task"}',
        'readprism_queue_depth{queue="scrape"}',
        "readprism_beat_up",
        "readprism_items_ingested_last_hour 1.0",
        "readprism_newest_item_age_seconds",
        'readprism_llm_calls_24h{outcome="ok"}',
        "readprism_llm_tokens_24h",
    ):
        assert series in body, series
    assert "readprism_llm_cost_usd_24h" not in body  # no price configured


@pytest.mark.asyncio
async def test_route_templates_not_raw_paths(client, token):
    await client.get(f"/api/v1/search/why/{uuid.uuid4()}")
    body = (await client.get("/metrics", headers={"X-Metrics-Token": token})).text
    assert 'route="/api/v1/search/why/{content_id}"' in body


@pytest.mark.asyncio
async def test_llm_calls_tokens_and_cost(db_session, monkeypatch):
    from app.services.llm.client import LLMClient

    def handler(request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "hi"}}], "usage": {"total_tokens": 1500}},
        )

    llm = LLMClient(api_key="k", transport=httpx.MockTransport(handler))
    from app.utils.cache import get_redis

    redis = get_redis()
    for key in await redis.keys("llm:*"):
        await redis.delete(key)
    assert await llm.complete(model="m", messages=[{"role": "user", "content": "x"}]) == "hi"
    monkeypatch.setattr(get_settings(), "llm_cost_per_million_tokens", 2.0)
    with patch("app.services.metrics.queues.queue_report") as report:
        report.return_value = {
            "queue_wait_seconds": {},
            "task_runtime_seconds": {},
            "digest_delivery": {"on_time_ratio": None},
        }
        body = (await prometheus.render(db_session, now=time.time())).decode()
    assert 'readprism_llm_calls_24h{outcome="ok"} 1.0' in body
    assert "readprism_llm_tokens_24h 1500.0" in body
    assert "readprism_llm_cost_usd_24h 0.003" in body
