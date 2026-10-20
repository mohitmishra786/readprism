"""Nightly rollup of first-party product metrics (#131)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.utils.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


async def _run(now: datetime | None = None) -> dict:
    from app.database import AsyncSessionLocal
    from app.services import product_metrics

    if not product_metrics.enabled():
        return {"status": "off"}
    yesterday = ((now or datetime.now(UTC)) - timedelta(days=1)).date()
    async with AsyncSessionLocal() as session:
        values = await product_metrics.rollup(session, yesterday)
        await session.commit()
    logger.info(f"Product metrics rolled up for {yesterday}")
    return {"day": yesterday.isoformat(), "metrics": len(values)}


@celery_app.task(name="app.workers.tasks.product_metrics.rollup_product_metrics")
def rollup_product_metrics() -> dict:
    return asyncio.run(_run())
