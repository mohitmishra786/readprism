"""Security controls fail closed when Redis is unavailable (#156)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import AsyncClient


class _BrokenRedis:
    async def incr(self, *_a, **_k):
        raise ConnectionError("redis down")

    async def expire(self, *_a, **_k):
        raise ConnectionError("redis down")

    async def set(self, *_a, **_k):
        raise ConnectionError("redis down")

    async def ping(self):
        raise ConnectionError("redis down")


@pytest.fixture
def redis_down(monkeypatch):
    from app.utils import cache, ratelimit

    monkeypatch.setattr(ratelimit.settings, "rate_limit_enabled", True)
    monkeypatch.setattr(ratelimit, "get_redis", lambda: _BrokenRedis())
    monkeypatch.setattr(cache, "get_redis", lambda: _BrokenRedis())


@pytest.mark.asyncio
async def test_login_is_refused_when_rate_limiter_cannot_count(client: AsyncClient, redis_down):
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "x@example.com", "password": "whatever123"}
    )
    assert resp.status_code == 503
    assert resp.headers.get("retry-after")


@pytest.mark.asyncio
async def test_non_auth_limits_still_fail_open(redis_down):
    from starlette.requests import Request

    from app.utils.ratelimit import RateLimiter

    limiter = RateLimiter(5, 60, "cosmetic")
    request = Request({"type": "http", "method": "POST", "headers": [], "client": ("1.2.3.4", 1)})
    await limiter(request)  # no exception


@pytest.mark.asyncio
async def test_webhook_replay_guard_rejects_when_redis_is_down(redis_down):
    from app.api.newsletter import _first_seen

    with pytest.raises(HTTPException) as exc:
        await _first_seen("newsletter:webhook:postmark:abc")
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_health_reports_degraded_without_redis(client: AsyncClient, redis_down):
    body = (await client.get("/health")).json()
    assert body["status"] == "degraded"
    assert body["redis"] is False
