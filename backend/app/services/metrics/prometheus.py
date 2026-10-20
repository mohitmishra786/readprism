"""Prometheus exposition for self-run monitoring (#170).

`GET /metrics` (token-gated like the JSON operator metrics) serves:

- HTTP request counts and latency by route template, from a middleware in
  this process;
- the queue telemetry behind GET /api/v1/metrics/queues (#239): queue wait
  and task runtime p50/p95, digest on-time ratio;
- queue depth, worker and beat heartbeat age (#234);
- ingestion: items fetched in the last hour, age of the newest item, sources
  by feed status;
- LLM calls and tokens over 24 h, and their cost when
  LLM_COST_PER_MILLION_TOKENS is set.

Everything except the HTTP series is computed at scrape time into a fresh
registry, because workers run in other processes; their numbers come from
Redis and the database.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import UTC, datetime, timedelta

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

__all__ = ["CONTENT_TYPE_LATEST", "HTTP_REGISTRY", "observe_request", "render"]

HTTP_REGISTRY = CollectorRegistry()
HTTP_REQUESTS = Counter(
    "readprism_http_requests",
    "HTTP requests by route template and status class.",
    ["method", "route", "status"],
    registry=HTTP_REGISTRY,
)
HTTP_LATENCY = Histogram(
    "readprism_http_request_duration_seconds",
    "HTTP request latency by route template.",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    registry=HTTP_REGISTRY,
)

LLM_CALLS_KEY = "llm:calls:{outcome}:{hour}"
LLM_TOKENS_KEY = "llm:tokens:{hour}"


def observe_request(method: str, route: str, status_code: int, seconds: float) -> None:
    HTTP_REQUESTS.labels(method, route, f"{status_code // 100}xx").inc()
    HTTP_LATENCY.labels(method, route).observe(seconds)


def _hours(now: float, n: int = 24) -> list[str]:
    from app.workers.queue_metrics import hour_key

    return [hour_key(now - 3600 * h) for h in range(n)]


async def record_llm_usage(ok: bool, tokens: int) -> None:
    """Hourly LLM call and token counters in Redis (all processes)."""
    from app.utils.cache import cache_incr
    from app.workers.queue_metrics import hour_key

    hour = hour_key(time.time())
    await cache_incr(
        LLM_CALLS_KEY.format(outcome="ok" if ok else "error", hour=hour), ttl_seconds=2 * 86400
    )
    if tokens:
        await cache_incr(LLM_TOKENS_KEY.format(hour=hour), tokens, ttl_seconds=2 * 86400)


async def _sum(redis, keys: list[str]) -> float:
    values = await redis.mget(keys)
    return float(sum(int(v) for v in values if v is not None))


async def render(session: AsyncSession, *, now: float | None = None, redis=None) -> bytes:
    from app.models.content import ContentItem
    from app.models.source import Source
    from app.services.metrics.queues import queue_report
    from app.utils.cache import cache_get, get_redis
    from app.workers.queue_metrics import _redis as sync_redis
    from app.workers.tasks.heartbeat import HEARTBEAT_KEY, WORKER_QUEUES, worker_key

    s = get_settings()
    now = now or time.time()
    redis = redis or get_redis()
    reg = CollectorRegistry()

    def gauge(name: str, doc: str, labels: tuple[str, ...] = ()) -> Gauge:
        return Gauge(name, doc, list(labels), registry=reg)

    # Queue telemetry (#239), last hour.
    report = await asyncio.to_thread(queue_report, sync_redis(), hours=1, now=now)
    wait = gauge("readprism_queue_wait_seconds", "Queue wait, last hour.", ("queue", "quantile"))
    for queue, stats in report["queue_wait_seconds"].items():
        for q in ("p50", "p95"):
            if stats[q] is not None:
                wait.labels(queue, q[1:]).set(stats[q])
    run = gauge("readprism_task_runtime_seconds", "Task runtime, last hour.", ("task", "quantile"))
    for task, stats in report["task_runtime_seconds"].items():
        for q in ("p50", "p95"):
            if stats[q] is not None:
                run.labels(task, q[1:]).set(stats[q])
    ratio = report["digest_delivery"]["on_time_ratio"]
    if ratio is not None:
        gauge("readprism_digest_on_time_ratio", "Digests delivered on time, last hour.").set(ratio)

    depth = gauge("readprism_queue_depth", "Jobs waiting per queue.", ("queue",))
    beat_age = gauge("readprism_heartbeat_age_seconds", "Seconds since a heartbeat.", ("process",))
    for queue in WORKER_QUEUES:
        with contextlib.suppress(Exception):
            depth.labels(queue).set(int(await redis.llen(queue)))
        seen = await cache_get(worker_key(queue))
        if seen is not None:
            beat_age.labels(f"worker-{queue}").set(max(0.0, now - float(seen)))
    beat = await cache_get(HEARTBEAT_KEY)
    gauge("readprism_beat_up", "1 while the beat heartbeat is fresh.").set(
        1 if beat is not None else 0
    )

    # Ingestion.
    hour_ago = datetime.fromtimestamp(now, UTC) - timedelta(hours=1)
    fetched = (
        await session.execute(
            select(func.count(ContentItem.id)).where(ContentItem.fetched_at >= hour_ago)
        )
    ).scalar() or 0
    gauge("readprism_items_ingested_last_hour", "Items fetched in the last hour.").set(fetched)
    latest = (await session.execute(select(func.max(ContentItem.fetched_at)))).scalar()
    if latest is not None:
        latest = latest if latest.tzinfo else latest.replace(tzinfo=UTC)
        gauge("readprism_newest_item_age_seconds", "Age of the newest item.").set(
            max(0.0, now - latest.timestamp())
        )
    sources = gauge("readprism_sources", "Active sources by feed status.", ("status",))
    for status, count in (
        await session.execute(
            select(Source.feed_status, func.count(Source.id))
            .where(Source.is_active.is_(True))
            .group_by(Source.feed_status)
        )
    ).all():
        sources.labels(status or "healthy").set(count)

    # LLM usage, last 24 h.
    hours = _hours(now)
    calls = gauge("readprism_llm_calls_24h", "LLM calls in the last 24 h.", ("outcome",))
    for outcome in ("ok", "error"):
        calls.labels(outcome).set(
            await _sum(redis, [LLM_CALLS_KEY.format(outcome=outcome, hour=h) for h in hours])
        )
    tokens = await _sum(redis, [LLM_TOKENS_KEY.format(hour=h) for h in hours])
    gauge("readprism_llm_tokens_24h", "LLM tokens in the last 24 h.").set(tokens)
    if s.llm_cost_per_million_tokens > 0:
        gauge("readprism_llm_cost_usd_24h", "Estimated LLM cost, last 24 h.").set(
            round(tokens / 1_000_000 * s.llm_cost_per_million_tokens, 4)
        )

    return generate_latest(HTTP_REGISTRY) + generate_latest(reg)
