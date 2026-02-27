from __future__ import annotations

import asyncio
import uuid

from app.workers.celery_app import celery_app
from app.utils.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.compute_prs.compute_prs_for_user_item", bind=True, max_retries=3)
def compute_prs_for_user_item(self, user_id: str, content_item_id: str) -> dict:
    return asyncio.run(_compute_prs_async(uuid.UUID(user_id), uuid.UUID(content_item_id)))


async def _compute_prs_async(user_id: uuid.UUID, content_item_id: uuid.UUID) -> dict:
    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem, UserContentInteraction
    from app.models.user import User
    from app.services.ranking.scorer import compute_prs
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return {"status": "user_not_found"}

        content_result = await session.execute(
            select(ContentItem).where(ContentItem.id == content_item_id)
        )
        content = content_result.scalar_one_or_none()
        if not content:
            return {"status": "content_not_found"}

        prs, breakdown = await compute_prs(content, user, session)

        # Store in UserContentInteraction
        interaction_result = await session.execute(
            select(UserContentInteraction).where(
                UserContentInteraction.user_id == user_id,
                UserContentInteraction.content_item_id == content_item_id,
            )
        )
        interaction = interaction_result.scalar_one_or_none()
        if interaction:
            interaction.prs_score = prs
        else:
            interaction = UserContentInteraction(
                user_id=user_id,
                content_item_id=content_item_id,
                prs_score=prs,
            )
            session.add(interaction)

        await session.commit()
        return {"status": "ok", "prs_score": prs}
