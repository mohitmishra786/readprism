"""Operator alert check (#171), every 10 minutes from beat.

Scheduled on both the scrape and digest queues, so a stopped worker on one
of them is still reported by the other; a Redis lock makes only the first
copy in each 10-minute window evaluate.
"""

from __future__ import annotations

import asyncio
import time

from app.workers.celery_app import celery_app

WINDOW_SECONDS = 600


async def _run() -> dict:
    from app.database import AsyncSessionLocal
    from app.services import alerts
    from app.utils.cache import cache_set_nx

    window = int(time.time() // WINDOW_SECONDS)
    if not await cache_set_nx(f"alerts:run:{window}", 1, ttl_seconds=WINDOW_SECONDS * 2):
        return {"skipped": "another worker ran this window"}
    async with AsyncSessionLocal() as session:
        return await alerts.run(session)


@celery_app.task(name="app.workers.tasks.alerts.check_alerts")
def check_alerts() -> dict:
    return asyncio.run(_run())
