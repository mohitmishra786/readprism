"""Raw reading-telemetry retention (#224).

What someone reads can reveal health, politics or religion, so raw
behavioural rows are kept only as long as ranking needs them:

- `digest_impressions` (one row per item shown, with features) older than
  TELEMETRY_RAW_RETENTION_DAYS are folded into `impression_rollups` (daily
  counts, no user) and deleted, in one transaction.
- On older interactions, the finest-grained reading fields (scroll depth,
  active time) are cleared. Completion, ratings and saves stay: ranking
  history and the interest graph are built from them.

The learner trains only on digests settled for 12 hours, so the window
(default 90 days) never removes data it has yet to use.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.utils.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

_ROLLUP = """
INSERT INTO impression_rollups (day, section, team, exploration, shown, viewed)
SELECT (shown_at AT TIME ZONE 'UTC')::date, coalesce(section, ''), coalesce(team, ''),
       coalesce(exploration, false), count(*), count(*) FILTER (WHERE viewed)
FROM digest_impressions
WHERE shown_at < :cutoff
GROUP BY 1, 2, 3, 4
ON CONFLICT (day, section, team, exploration) DO UPDATE
SET shown = impression_rollups.shown + EXCLUDED.shown,
    viewed = impression_rollups.viewed + EXCLUDED.viewed
"""


async def _prune_telemetry_async(now: datetime | None = None) -> dict:
    from sqlalchemy import delete, or_, text, update

    from app.database import AsyncSessionLocal
    from app.models.content import UserContentInteraction
    from app.models.digest import DigestImpression

    days = get_settings().telemetry_raw_retention_days
    if days <= 0:
        return {"status": "disabled"}
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)

    async with AsyncSessionLocal() as session:
        await session.execute(text(_ROLLUP), {"cutoff": cutoff})
        deleted = await session.execute(
            delete(DigestImpression).where(DigestImpression.shown_at < cutoff)
        )
        cleared = await session.execute(
            update(UserContentInteraction)
            .where(
                UserContentInteraction.updated_at < cutoff,
                or_(
                    UserContentInteraction.scroll_depth_pct.isnot(None),
                    UserContentInteraction.active_time_seconds.isnot(None),
                ),
            )
            .values(scroll_depth_pct=None, active_time_seconds=None)
            .execution_options(synchronize_session=False)
        )
        await session.commit()
    result = {
        "status": "ok",
        "impressions_rolled_up": int(getattr(deleted, "rowcount", 0) or 0),
        "interactions_coarsened": int(getattr(cleared, "rowcount", 0) or 0),
    }
    logger.info(f"Telemetry retention ({days}d): {result}")
    return result


@celery_app.task(name="app.workers.tasks.prune_telemetry.prune_raw_telemetry")
def prune_raw_telemetry() -> dict:
    return asyncio.run(_prune_telemetry_async())
