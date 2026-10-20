"""The async Redis client survives one asyncio.run() per Celery task (#323)."""

from __future__ import annotations

import asyncio
import uuid


def test_cache_works_across_separate_event_loops():
    from app.utils import cache

    cache._redis_client = None
    key = f"loop-test:{uuid.uuid4().hex}"
    results = []
    for i in range(4):  # like four tasks in one solo worker
        results.append(asyncio.run(cache.cache_set(key, i, ttl_seconds=30)))
        assert asyncio.run(cache.cache_get(key)) == i
    assert results == [True] * 4
    asyncio.run(cache.cache_delete(key))
