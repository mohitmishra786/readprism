"""Redis-backed fixed-window rate limiting (audit 06-4).

Used as a FastAPI dependency on abuse-prone endpoints (auth). Keyed on the
client IP so credential-stuffing and registration-spam from one source are
throttled. Fails **open** on a Redis error — a cache outage must not lock every
user out of login — since rate limiting is a mitigation, not the auth gate.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.config import get_settings
from app.utils.cache import get_redis
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


def _client_ip(request: Request) -> str:
    """Best-effort client IP, honouring a single proxy's X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """FastAPI dependency enforcing `max_requests` per `window_seconds` per IP."""

    def __init__(self, max_requests: int, window_seconds: int, scope: str) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.scope = scope

    async def __call__(self, request: Request) -> None:
        if not settings.rate_limit_enabled or self.max_requests <= 0:
            return
        ip = _client_ip(request)
        key = f"ratelimit:{self.scope}:{ip}"
        try:
            redis = get_redis()
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, self.window_seconds)
        except Exception as e:  # pragma: no cover - fail open on cache errors
            logger.warning(f"Rate limiter unavailable ({e}); allowing request")
            return
        if count > self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(self.window_seconds)},
            )
