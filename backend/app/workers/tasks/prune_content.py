"""Data-retention pruning of stored full article text (audit 08-3).

Holding full third-party article/newsletter text indefinitely is the highest
copyright-exposure behaviour in the product. This scheduled task truncates
`full_text` to a short excerpt once content is older than the retention window,
keeping the summary + link + excerpt (which is what the reader/digest actually
need) but dropping the indefinite full copy.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.utils.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


async def _prune_full_text_async() -> dict:
    from sqlalchemy import func, update

    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem

    settings = get_settings()
    retention_days = settings.content_full_text_retention_days
    if retention_days <= 0:
        return {"status": "disabled", "pruned": 0}

    excerpt_chars = settings.content_excerpt_chars
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)

    async with AsyncSessionLocal() as session:
        # Only touch rows still holding more than an excerpt's worth of text, so
        # the job is idempotent (re-running never re-truncates the same row).
        result = await session.execute(
            update(ContentItem)
            .where(
                ContentItem.fetched_at < cutoff,
                ContentItem.full_text.is_not(None),
                func.length(ContentItem.full_text) > excerpt_chars,
            )
            .values(full_text=func.left(ContentItem.full_text, excerpt_chars))
        )
        pruned = result.rowcount or 0
        await session.commit()

    logger.info(f"Pruned full_text on {pruned} content items older than {retention_days}d")
    return {"status": "ok", "pruned": pruned}


@celery_app.task(name="app.workers.tasks.prune_content.prune_old_full_text")
def prune_old_full_text() -> dict:
    return asyncio.run(_prune_full_text_async())
