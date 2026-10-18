"""Daily discovery-pool refresh (#141). Runs on the scrape queue: it fetches pages."""

from __future__ import annotations

import asyncio
import uuid

from app.utils.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.discovery.refresh_discovery_pools")
def refresh_discovery_pools() -> dict:
    return asyncio.run(_refresh_all())


@celery_app.task(name="app.workers.tasks.discovery.refresh_discovery_for_user")
def refresh_discovery_for_user(user_id: str) -> dict:
    return asyncio.run(_refresh_all(only=uuid.UUID(user_id)))


async def _refresh_all(only: uuid.UUID | None = None) -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.discovery.pool import refresh_for_user
    from app.workers.tasks.ingest_feeds import _enqueue_embeddings, _safe_rollback

    async with AsyncSessionLocal() as session:
        query = select(User.id).where(User.onboarding_complete == True)
        if only is not None:
            query = select(User.id).where(User.id == only)
        user_ids = [row[0] for row in (await session.execute(query)).all()]

    feed_cache: dict = {}  # one fetch per pack feed per run, shared across users
    total = 0
    for user_id in user_ids:
        async with AsyncSessionLocal() as session:
            try:
                new_ids = await refresh_for_user(user_id, session, feed_cache=feed_cache)
                await session.commit()
            except Exception as e:
                await _safe_rollback(session, f"discovery {user_id}")
                logger.error(f"discovery refresh failed for {user_id}: {e}")
                continue
        _enqueue_embeddings(new_ids)
        total += len(new_ids)
    return {"users": len(user_ids), "new_items": total}
