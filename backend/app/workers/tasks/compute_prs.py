from __future__ import annotations

import asyncio
import uuid

from app.workers.celery_app import celery_app
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Pre-compute PRS for content ingested within this many hours
PRS_PRECOMPUTE_WINDOW_HOURS = 26  # slightly more than one daily cycle


@celery_app.task(name="app.workers.tasks.compute_prs.compute_prs_for_user_item", bind=True, max_retries=3)
def compute_prs_for_user_item(self, user_id: str, content_item_id: str) -> dict:
    return asyncio.run(_compute_prs_async(uuid.UUID(user_id), uuid.UUID(content_item_id)))


@celery_app.task(name="app.workers.tasks.compute_prs.precompute_prs_for_active_users")
def precompute_prs_for_active_users() -> dict:
    """
    Periodic background task: for each active user, enqueue individual PRS
    computations for all content items ingested in the last 26 hours that do
    not yet have a PRS score for that user.

    Running this every 2 hours means PRS scores are always fresh when digest
    generation runs, avoiding expensive real-time computation on 500+ items.
    """
    return asyncio.run(_precompute_batch_async())


async def _precompute_batch_async() -> dict:
    from datetime import datetime, timezone, timedelta

    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem, UserContentInteraction
    from app.models.user import User
    from sqlalchemy import select, exists

    cutoff = datetime.now(timezone.utc) - timedelta(hours=PRS_PRECOMPUTE_WINDOW_HOURS)

    async with AsyncSessionLocal() as session:
        # Active users = onboarding complete + active in last 7 days
        activity_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        users_result = await session.execute(
            select(User.id).where(
                User.onboarding_complete == True,
                User.updated_at >= activity_cutoff,
            )
        )
        user_ids = [row[0] for row in users_result.all()]

        # Recent content items (with embeddings = ready for ranking)
        content_result = await session.execute(
            select(ContentItem.id).where(
                ContentItem.fetched_at >= cutoff,
            ).limit(500)
        )
        content_ids = [row[0] for row in content_result.all()]

        if not user_ids or not content_ids:
            return {"queued": 0, "users": len(user_ids), "items": len(content_ids)}

        # For each user, enqueue only items without an existing PRS score
        queued = 0
        for user_id in user_ids:
            for content_id in content_ids:
                # Check if interaction with PRS score already exists
                check = await session.execute(
                    select(UserContentInteraction.id).where(
                        UserContentInteraction.user_id == user_id,
                        UserContentInteraction.content_item_id == content_id,
                        UserContentInteraction.prs_score.isnot(None),
                    ).limit(1)
                )
                if check.scalar_one_or_none() is None:
                    compute_prs_for_user_item.delay(str(user_id), str(content_id))
                    queued += 1

        logger.info(
            f"PRS pre-compute: queued {queued} tasks for "
            f"{len(user_ids)} users × {len(content_ids)} items"
        )
        return {"queued": queued, "users": len(user_ids), "items": len(content_ids)}


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
