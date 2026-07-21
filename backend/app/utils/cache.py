from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_redis_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def cache_get(key: str) -> Any | None:
    client = get_redis()
    try:
        value = await client.get(key)
        if value is not None:
            return json.loads(value)
        return None
    except Exception as e:
        logger.warning(f"Redis GET failed for key {key}: {e}")
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int = 3600) -> bool:
    client = get_redis()
    try:
        serialized = json.dumps(value, default=str)
        await client.setex(key, ttl_seconds, serialized)
        return True
    except Exception as e:
        logger.warning(f"Redis SET failed for key {key}: {e}")
        return False


async def cache_set_nx(key: str, value: Any, ttl_seconds: int) -> bool:
    """Atomically set `key` only if absent (SET NX EX). Returns True if the key
    was newly set, False if it already existed. Used for replay-attack dedupe.

    On a Redis error we return True (fail-open on the dedupe layer) so that a
    cache outage never silently drops legitimate, already-signature-verified
    webhooks; the HMAC signature remains the authoritative gate.
    """
    client = get_redis()
    try:
        serialized = json.dumps(value, default=str)
        result = await client.set(key, serialized, ex=ttl_seconds, nx=True)
        return bool(result)
    except Exception as e:
        logger.warning(f"Redis SET NX failed for key {key}: {e}")
        return True


async def cache_delete(key: str) -> bool:
    client = get_redis()
    try:
        await client.delete(key)
        return True
    except Exception as e:
        logger.warning(f"Redis DELETE failed for key {key}: {e}")
        return False


async def cache_exists(key: str) -> bool:
    client = get_redis()
    try:
        return bool(await client.exists(key))
    except Exception as e:
        logger.warning(f"Redis EXISTS failed for key {key}: {e}")
        return False


async def ping_redis() -> bool:
    client = get_redis()
    try:
        await client.ping()
        return True
    except Exception:
        return False
