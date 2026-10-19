"""Large OPML imports in the background, with progress (#202).

The request parses the file, de-duplicates against the user's sources and
checks plan limits (fast, and errors belong in the response). Imports over
QUEUE_AFTER outlines then run here, inserting in batches and recording
progress in Redis, so a 2,000-feed Feedly export never hits a request
timeout. GET /sources/import-jobs/{id} reads the progress.
"""

from __future__ import annotations

import asyncio
import uuid

from app.utils.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

BATCH = 100
JOB_TTL_SECONDS = 24 * 3600


def job_key(job_id: str) -> str:
    return f"opml-import:{job_id}"


def payload_key(job_id: str) -> str:
    return f"opml-import:{job_id}:feeds"


async def create_job(user_id: uuid.UUID, feeds: list[dict]) -> str:
    """Store the planned feeds and initial progress; returns the job id."""
    from app.utils.cache import cache_set

    job_id = uuid.uuid4().hex
    await cache_set(payload_key(job_id), feeds, ttl_seconds=JOB_TTL_SECONDS)
    await cache_set(
        job_key(job_id),
        {"user_id": str(user_id), "status": "queued", "total": len(feeds), "done": 0},
        ttl_seconds=JOB_TTL_SECONDS,
    )
    return job_id


@celery_app.task(name="app.workers.tasks.import_jobs.run_opml_import")
def run_opml_import(job_id: str) -> dict:
    return asyncio.run(_run_opml_import(job_id))


async def _run_opml_import(job_id: str) -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.source import Source
    from app.utils.cache import cache_get, cache_set

    state = await cache_get(job_key(job_id))
    feeds = await cache_get(payload_key(job_id))
    if not state or feeds is None:
        logger.warning(f"OPML import job {job_id} not found or expired")
        return {"status": "missing"}
    user_id = uuid.UUID(state["user_id"])
    state["status"] = "running"
    await cache_set(job_key(job_id), state, ttl_seconds=JOB_TTL_SECONDS)

    created = 0
    try:
        for start in range(0, len(feeds), BATCH):
            batch = feeds[start : start + BATCH]
            async with AsyncSessionLocal() as session:
                # Re-check per batch: the user may have added some meanwhile.
                have = {
                    row[0]
                    for row in (
                        await session.execute(select(Source.url).where(Source.user_id == user_id))
                    ).all()
                }
                for feed in batch:
                    if feed["url"] in have:
                        continue
                    session.add(
                        Source(
                            user_id=user_id,
                            url=feed["url"],
                            name=feed["title"],
                            feed_url=feed["url"],
                            source_type="rss",
                            tags=feed.get("tags") or [],
                            initial_backfill_done=False,
                        )
                    )
                    have.add(feed["url"])
                    created += 1
                await session.commit()
            state.update(done=min(start + BATCH, len(feeds)), created=created)
            await cache_set(job_key(job_id), state, ttl_seconds=JOB_TTL_SECONDS)
    except Exception as e:
        logger.error(f"OPML import job {job_id} failed after {created} feeds: {e}")
        state.update(status="failed", error="The import stopped part-way; try again.")
        await cache_set(job_key(job_id), state, ttl_seconds=JOB_TTL_SECONDS)
        return {"status": "failed", "created": created}

    state.update(status="done", done=len(feeds), created=created)
    await cache_set(job_key(job_id), state, ttl_seconds=JOB_TTL_SECONDS)
    if created:
        from app.workers.tasks.ingest_feeds import ingest_user_sources

        ingest_user_sources.delay(str(user_id))
    return {"status": "done", "created": created}
