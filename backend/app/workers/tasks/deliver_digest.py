from __future__ import annotations

import asyncio
import uuid

from app.workers.celery_app import celery_app
from app.utils.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.deliver_digest.deliver_digest_task", bind=True, max_retries=3)
def deliver_digest_task(self, digest_id: str) -> dict:
    return asyncio.run(_deliver_digest_async(uuid.UUID(digest_id)))


async def _deliver_digest_async(digest_id: uuid.UUID) -> dict:
    from app.database import AsyncSessionLocal
    from app.models.digest import Digest
    from app.models.user import User
    from app.services.digest.delivery import deliver_digest
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Digest).where(Digest.id == digest_id))
        digest = result.scalar_one_or_none()
        if not digest:
            return {"status": "digest_not_found"}

        user_result = await session.execute(select(User).where(User.id == digest.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return {"status": "user_not_found"}

        success = await deliver_digest(digest, user, session)
        await session.commit()
        return {"status": "ok" if success else "failed", "digest_id": str(digest_id)}
