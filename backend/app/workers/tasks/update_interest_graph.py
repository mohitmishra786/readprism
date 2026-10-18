from __future__ import annotations

import asyncio
import uuid

from app.utils.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)
MIN_INTERACTIONS_FOR_META_UPDATE = 20


@celery_app.task(
    name="app.workers.tasks.update_interest_graph.update_interest_graph_for_interaction",
    bind=True,
    max_retries=3,
)
def update_interest_graph_for_interaction(self, interaction_id: str) -> dict:
    return asyncio.run(_update_graph_async(uuid.UUID(interaction_id)))


async def _update_graph_async(interaction_id: uuid.UUID) -> dict:
    from sqlalchemy import func, select

    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem, UserContentInteraction
    from app.services.interest_graph.updater import update_from_interaction

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
            await _enqueue_meta_weights_update(interaction.user_id)

        return {"status": "ok", "interaction_id": str(interaction_id)}


# A burst of interactions (several telemetry flushes, a few ratings) should
# produce one weight update, run after the burst settles (#104).
META_UPDATE_DEBOUNCE_SECONDS = 300
META_UPDATE_DELAY_SECONDS = 60
# Train on the most recent digest rows only.
META_TRAINING_WINDOW = 100


def _meta_debounce_key(user_id: uuid.UUID) -> str:
    return f"meta-weights-pending:{user_id}"


async def _enqueue_meta_weights_update(user_id: uuid.UUID) -> bool:
    """Schedule one delayed weight update per user per debounce window."""
    from app.utils.cache import cache_set_nx

    if not await cache_set_nx(_meta_debounce_key(user_id), 1, META_UPDATE_DEBOUNCE_SECONDS):
        return False
    update_meta_weights_task.apply_async(args=[str(user_id)], countdown=META_UPDATE_DELAY_SECONDS)
    return True


@celery_app.task(name="app.workers.tasks.update_interest_graph.update_meta_weights_task")
def update_meta_weights_task(user_id: str) -> dict:
    return asyncio.run(_update_meta_weights_async(uuid.UUID(user_id)))


async def _update_meta_weights_async(user_id: uuid.UUID) -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.content import UserContentInteraction
    from app.models.digest import Digest, DigestItem
    from app.services.ranking.meta_weights import update_meta_weights
    from app.utils.cache import cache_delete

    # Re-arm the debounce so interactions arriving from now on schedule the
    # next update instead of being absorbed by this one.
    await cache_delete(_meta_debounce_key(user_id))

    async with AsyncSessionLocal() as session:
        # Only this user's digests: a shared public item also appears in other
        # users' digests with *their* signal breakdowns, and pairing those with
        # this user's reading trained one user's weights on another's
        # features (#104).
        result = await session.execute(
            select(DigestItem, UserContentInteraction)
            .join(Digest, Digest.id == DigestItem.digest_id)
            .join(
                UserContentInteraction,
                (UserContentInteraction.content_item_id == DigestItem.content_item_id)
                & (UserContentInteraction.user_id == user_id),
            )
            .where(Digest.user_id == user_id)
            .order_by(Digest.generated_at.desc(), DigestItem.position.asc())
            .limit(META_TRAINING_WINDOW)
        )
        pairs = [(row[0], row[1]) for row in result.fetchall()]
        await update_meta_weights(user_id, pairs, session)
        await session.commit()
        return {"status": "ok", "user_id": str(user_id)}


@celery_app.task(name="app.workers.tasks.update_interest_graph.apply_decay_all_users")
def apply_decay_all_users() -> dict:
    return asyncio.run(_apply_decay_async())


async def _apply_decay_async() -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.interest_graph.decay import apply_decay

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User.id))
        user_ids = [row[0] for row in result.fetchall()]
        for uid in user_ids:
            await apply_decay(uid, session)
        await session.commit()
        return {"status": "ok", "users_processed": len(user_ids)}
