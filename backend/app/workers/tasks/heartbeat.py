"""Beat liveness heartbeat (audit 07-4).

Beat is a scheduler, not a worker, so it can't answer `celery inspect ping`. A
dead beat silently stops all ingestion and digests. This task is scheduled every
minute; it writes a short-TTL key to Redis. If beat stops scheduling (or no
worker is consuming), the key expires and the beat container's healthcheck fails.
"""

from __future__ import annotations

import asyncio
import time

from app.utils.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

HEARTBEAT_KEY = "beat:heartbeat"
HEARTBEAT_TTL_SECONDS = 180


async def _write_heartbeat() -> dict:
    from app.utils.cache import cache_set

    ts = int(time.time())
    await cache_set(HEARTBEAT_KEY, ts, ttl_seconds=HEARTBEAT_TTL_SECONDS)
    return {"heartbeat": ts}


@celery_app.task(name="app.workers.tasks.heartbeat.beat_heartbeat")
def beat_heartbeat() -> dict:
    return asyncio.run(_write_heartbeat())
