from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, time, timedelta

from app.config import get_settings
from app.utils.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

# ±15 minutes around a preferred local time counts as "the send window".
SEND_WINDOW_MINUTES = 15
# Evidence needed before the learned send-hour job moves a user's time.
LEARN_MIN_OPENS = 30
LEARN_LOOKBACK_DAYS = 90


@celery_app.task(
    name="app.workers.tasks.build_digest.build_digest_for_user", bind=True, max_retries=2
)
def build_digest_for_user(self, user_id: str) -> dict:
    return asyncio.run(_build_digest_async(uuid.UUID(user_id)))


def _dedupe_window(frequency: str) -> timedelta:
    """How long a just-built digest makes the next build a duplicate.

    Sized to half the shortest interval a frequency implies, so a Celery
    retry (seconds later) or a double-scheduled beat run can never send two
    digests, while the next legitimate slot always builds.
    """
    if frequency == "weekly":
        return timedelta(hours=84)
    if frequency == "twice_daily":
        return timedelta(hours=6)
    return timedelta(hours=12)  # daily and anything unrecognized


def _should_deliver_email(user, digest) -> bool:
    if user.digest_frequency == "in_app_only":
        return False
    # "Nothing worth reading": a near-empty digest is not worth an email.
    # It stays available in-app (UX-03).
    return (digest.total_items or 0) >= get_settings().digest_min_items


async def _build_digest_async(user_id: uuid.UUID) -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.digest import Digest
    from app.models.user import User
    from app.services.digest.builder import build_digest
    from app.utils.cache import cache_delete, cache_set_nx

    # Serialize builds per user: two overlapping tasks could both pass the
    # dedupe lookup before either commits and send two digests (CodeRabbit).
    # NX + TTL means a crashed holder cannot deadlock the user forever.
    lock_key = f"digest-build-lock:{user_id}"
    if not await cache_set_nx(lock_key, "1", ttl_seconds=600):
        logger.info(f"Digest build for user {user_id} skipped: another build holds the lock")
        return {"status": "build_in_progress"}

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return {"status": "user_not_found"}

            # Idempotency: a retry (or double-scheduled run) inside the window
            # returns the existing digest instead of building a second one.
            window = _dedupe_window(user.digest_frequency)
            recent = await session.execute(
                select(Digest)
                .where(
                    Digest.user_id == user.id,
                    Digest.generated_at >= datetime.now(UTC) - window,
                )
                .order_by(Digest.generated_at.desc())
                .limit(1)
            )
            existing = recent.scalar_one_or_none()
            if existing is not None:
                logger.info(
                    f"Duplicate digest build skipped for user {user.id}: "
                    f"digest {existing.id} is inside the {window} window"
                )
                # Delivery recovery: if the previous build committed but died
                # before enqueuing delivery, this retry re-enqueues it. The
                # delivery task itself is idempotent (delivered_at check), so
                # a duplicate enqueue cannot double-send.
                if existing.delivered_at is None and _should_deliver_email(user, existing):
                    from app.workers.tasks.deliver_digest import deliver_digest_task

                    deliver_digest_task.delay(str(existing.id))
                return {"status": "duplicate_skipped", "digest_id": str(existing.id)}

            digest = await build_digest(user, session)
            await session.commit()

            if _should_deliver_email(user, digest):
                from app.workers.tasks.deliver_digest import deliver_digest_task

                deliver_digest_task.delay(str(digest.id))
            else:
                logger.info(
                    f"Email skipped for digest {digest.id} of user {user.id}: "
                    f"{digest.total_items} items (min "
                    f"{get_settings().digest_min_items}) or frequency "
                    f"{user.digest_frequency}"
                )

            return {"status": "ok", "digest_id": str(digest.id)}
    finally:
        await cache_delete(lock_key)


def _preferred_slots(user) -> list[time]:
    """Local times a digest should be sent for this user's frequency."""
    slots = [user.digest_time_morning]
    if getattr(user, "digest_frequency", "daily") == "twice_daily":
        evening = (
            datetime.combine(datetime.min, user.digest_time_morning) + timedelta(hours=12)
        ).time()
        slots.append(evening)
    return slots


def _is_digest_time_for_user(user, *, now: datetime | None = None) -> bool:
    """
    Return True if the current local time is within the send window of any
    preferred slot for the user's frequency (DST-safe via zoneinfo).

    `now` is injectable for tests; production uses the real clock.
    """
    import zoneinfo

    try:
        tz = zoneinfo.ZoneInfo(user.timezone or "UTC")
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")

    now_local = (now or datetime.now(tz)).astimezone(tz)
    now_minutes = now_local.hour * 60 + now_local.minute
    for preferred in _preferred_slots(user):
        diff_minutes = abs(now_minutes - preferred.hour * 60 - preferred.minute)
        # Handle midnight wrap-around
        diff_minutes = min(diff_minutes, 1440 - diff_minutes)
        if diff_minutes <= SEND_WINDOW_MINUTES:
            return True
    return False


@celery_app.task(name="app.workers.tasks.build_digest.schedule_daily_digests")
def schedule_daily_digests() -> dict:
    return asyncio.run(_schedule_digests_async())


async def _schedule_digests_async() -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.user import User

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.onboarding_complete == True))
        users = list(result.scalars().all())

        queued = 0
        for user in users:
            # Only build digest for users whose local time matches their preferred time
            if _is_digest_time_for_user(user):
                build_digest_for_user.delay(str(user.id))
                queued += 1

        logger.info(f"Scheduled {queued} daily digests (timezone-aware)")
        return {"queued": queued}


@celery_app.task(name="app.workers.tasks.build_digest.learn_send_times")
def learn_send_times() -> dict:
    """Weekly: move each user's send time to their learned open-time peak."""
    return asyncio.run(_learn_send_times_async())


async def _learn_send_times_async() -> dict:
    import zoneinfo

    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.content import UserContentInteraction
    from app.models.user import User
    from app.services.ranking.phase2.contract import preferred_hour

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.onboarding_complete == True, User.send_time_locked == False)
        )
        users = list(result.scalars().all())

        cutoff = datetime.now(UTC) - timedelta(days=LEARN_LOOKBACK_DAYS)
        updated = 0
        for user in users:
            opens_result = await session.execute(
                select(UserContentInteraction.opened_at).where(
                    UserContentInteraction.user_id == user.id,
                    UserContentInteraction.opened_at.isnot(None),
                    UserContentInteraction.opened_at >= cutoff,
                )
            )
            opened_at_rows = [row[0] for row in opens_result.all() if row[0] is not None]
            if len(opened_at_rows) < LEARN_MIN_OPENS:
                continue

            try:
                tz = zoneinfo.ZoneInfo(user.timezone or "UTC")
            except Exception:
                tz = zoneinfo.ZoneInfo("UTC")

            local_hours = [opened.astimezone(tz).hour for opened in opened_at_rows]
            learned = preferred_hour(local_hours, default=user.digest_time_morning.hour)
            if learned != user.digest_time_morning.hour:
                user.digest_time_morning = time(learned, 0)
                updated += 1
                logger.info(
                    f"Learned send time {learned}:00 local for user {user.id} "
                    f"({len(local_hours)} opens)"
                )

        await session.commit()
        return {"users_checked": len(users), "send_times_updated": updated}
