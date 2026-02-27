from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.utils.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.build_digest.build_digest_for_user", bind=True, max_retries=2)
def build_digest_for_user(self, user_id: str) -> dict:
    return asyncio.run(_build_digest_async(uuid.UUID(user_id)))


async def _build_digest_async(user_id: uuid.UUID) -> dict:
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.digest.builder import build_digest
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return {"status": "user_not_found"}

        digest = await build_digest(user, session)
        await session.commit()

        # Enqueue email delivery only if user wants email delivery
        if user.digest_frequency != "in_app_only":
            from app.workers.tasks.deliver_digest import deliver_digest_task
            deliver_digest_task.delay(str(digest.id))

        return {"status": "ok", "digest_id": str(digest.id)}


def _is_digest_time_for_user(user) -> bool:
    """
    Return True if the current UTC time is within ±15 minutes of the user's
    preferred digest time in their local timezone.
    """
    import zoneinfo

    try:
        tz = zoneinfo.ZoneInfo(user.timezone or "UTC")
    except Exception:
        tz = timezone.utc

    now_local = datetime.now(tz)
    preferred = user.digest_time_morning  # datetime.time object, e.g. 07:00
    # Allow a ±15-minute window
    diff_minutes = abs(
        now_local.hour * 60 + now_local.minute
        - preferred.hour * 60 - preferred.minute
    )
    # Handle midnight wrap-around
    diff_minutes = min(diff_minutes, 1440 - diff_minutes)
    return diff_minutes <= 15


@celery_app.task(name="app.workers.tasks.build_digest.schedule_daily_digests")
def schedule_daily_digests() -> dict:
    return asyncio.run(_schedule_digests_async())


async def _schedule_digests_async() -> dict:
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.onboarding_complete == True)
        )
        users = list(result.scalars().all())

        queued = 0
        for user in users:
            # Only build digest for users whose local time matches their preferred time
            if _is_digest_time_for_user(user):
                build_digest_for_user.delay(str(user.id))
                queued += 1

        logger.info(f"Scheduled {queued} daily digests (timezone-aware)")
        return {"queued": queued}
