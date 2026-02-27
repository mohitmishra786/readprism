from __future__ import annotations

import asyncio
import uuid

from app.workers.celery_app import celery_app
from app.utils.logging import get_logger

logger = get_logger(__name__)
MIN_INTERACTIONS_FOR_META_UPDATE = 20


@celery_app.task(
    name="app.workers.tasks.update_interest_graph.update_interest_graph_for_interaction",
    bind=True, max_retries=3
)
def update_interest_graph_for_interaction(self, interaction_id: str) -> dict:
    return asyncio.run(_update_graph_async(uuid.UUID(interaction_id)))


async def _update_graph_async(interaction_id: uuid.UUID) -> dict:
    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem, UserContentInteraction
    from app.services.interest_graph.updater import update_from_interaction
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserContentInteraction).where(UserContentInteraction.id == interaction_id)
        )
        interaction = result.scalar_one_or_none()
        if not interaction:
            return {"status": "not_found"}

        content_result = await session.execute(
            select(ContentItem).where(ContentItem.id == interaction.content_item_id)
        )
        content = content_result.scalar_one_or_none()
        if not content:
            return {"status": "content_not_found"}

        await update_from_interaction(interaction, content, session)

        # Check if user has enough interactions to update meta weights
        count_result = await session.execute(
            select(func.count(UserContentInteraction.id)).where(
                UserContentInteraction.user_id == interaction.user_id
            )
        )
        count = count_result.scalar() or 0

        await session.commit()

        if count > MIN_INTERACTIONS_FOR_META_UPDATE:
            update_meta_weights_task.delay(str(interaction.user_id))

        return {"status": "ok", "interaction_id": str(interaction_id)}


@celery_app.task(
    name="app.workers.tasks.update_interest_graph.update_meta_weights_task"
)
def update_meta_weights_task(user_id: str) -> dict:
    return asyncio.run(_update_meta_weights_async(uuid.UUID(user_id)))


async def _update_meta_weights_async(user_id: uuid.UUID) -> dict:
    from app.database import AsyncSessionLocal
    from app.models.content import UserContentInteraction
    from app.models.digest import DigestItem
    from app.services.ranking.meta_weights import update_meta_weights
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DigestItem, UserContentInteraction)
            .join(
                UserContentInteraction,
                (UserContentInteraction.content_item_id == DigestItem.content_item_id)
                & (UserContentInteraction.user_id == user_id),
            )
            .limit(100)
        )
        pairs = [(row[0], row[1]) for row in result.fetchall()]
        await update_meta_weights(user_id, pairs, session)
        await session.commit()
        return {"status": "ok", "user_id": str(user_id)}


@celery_app.task(
    name="app.workers.tasks.update_interest_graph.apply_decay_all_users"
)
def apply_decay_all_users() -> dict:
    return asyncio.run(_apply_decay_async())


async def _apply_decay_async() -> dict:
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.interest_graph.decay import apply_decay
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User.id))
        user_ids = [row[0] for row in result.fetchall()]
        for uid in user_ids:
            await apply_decay(uid, session)
        await session.commit()
        return {"status": "ok", "users_processed": len(user_ids)}
