#!/usr/bin/env python
"""Load-test scheduled digest builds on a running stack (#239).

Seeds N synthetic onboarded users who all follow one synthetic feed with
fresh items (no network), queues their digest builds exactly as the daily
scheduler does (with an `rp_due_at` header), waits for the workers, and
reports how late each digest was built against DIGEST_ON_TIME_SECONDS.
Queue wait and runtimes are printed from the same telemetry as
/api/v1/metrics/queues.

    docker compose up -d --scale worker-digest=4
    docker compose exec backend python scripts/load_test_digests.py --users 1000

Rows are tagged with a unique prefix and deleted afterwards (--keep to keep
them). Digest emails are not sent: synthetic users have no verified address
and the run uses .invalid domains.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
import uuid
from datetime import UTC, datetime, timedelta

_VOCAB = (
    "kernel scheduler latency cache vector index planner rust compiler tokenizer "
    "gradient dataset privacy cipher router packet storage replica consensus "
    "typography layout color motion pricing churn hiring growth design garden "
    "climate ocean battery solar transit housing budget museum novel poetry"
).split()


async def _seed(prefix: str, n_users: int, n_items: int) -> list[uuid.UUID]:
    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem
    from app.models.feed import Feed
    from app.models.source import Source
    from app.models.user import User

    feed_url = f"https://{prefix}.loadtest.invalid/rss"
    async with AsyncSessionLocal() as session:
        feed = Feed(key=feed_url, url=feed_url, feed_url=feed_url)
        session.add(feed)
        await session.flush()
        now = datetime.now(UTC)
        rng = random.Random(prefix)
        for i in range(n_items):
            # Distinct words per item, so story synthesis doesn't fold them together.
            words = rng.sample(_VOCAB, 8)
            session.add(
                ContentItem(
                    feed_id=feed.id,
                    url=f"{feed_url}/{i}",
                    title=" ".join(words[:4]).capitalize(),
                    summary_brief=" ".join(words).capitalize() + ".",
                    summary_source="extractive",
                    topic_clusters=[f"topic-{i % 12}"],
                    fetched_at=now - timedelta(minutes=i),
                    word_count=600,
                    extraction_method="feed",
                )
            )
        ids: list[uuid.UUID] = []
        for i in range(n_users):
            user = User(
                email=f"{prefix}-{i}@loadtest.invalid",
                hashed_password="x",
                onboarding_complete=True,
            )
            session.add(user)
            await session.flush()
            session.add(Source(user_id=user.id, url=feed_url, feed_url=feed_url, feed_id=feed.id))
            ids.append(user.id)
        await session.commit()
    return ids


async def _wait(user_ids: list[uuid.UUID], timeout: float) -> dict[uuid.UUID, datetime]:
    from sqlalchemy import func, select

    from app.database import AsyncSessionLocal
    from app.models.digest import Digest

    deadline = time.time() + timeout
    built: dict[uuid.UUID, datetime] = {}
    while time.time() < deadline:
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(Digest.user_id, func.min(Digest.generated_at))
                    .where(Digest.user_id.in_(user_ids))
                    .group_by(Digest.user_id)
                )
            ).all()
        built = dict(rows)
        print(f"\r{len(built)}/{len(user_ids)} digests built", end="", flush=True)
        if len(built) == len(user_ids):
            break
        await asyncio.sleep(2)
    print()
    return built


async def _cleanup(prefix: str) -> None:
    from sqlalchemy import delete

    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem
    from app.models.feed import Feed
    from app.models.user import User

    async with AsyncSessionLocal() as session:
        await session.execute(delete(User).where(User.email.like(f"{prefix}-%@loadtest.invalid")))
        await session.execute(
            delete(ContentItem).where(ContentItem.url.like(f"https://{prefix}.%"))
        )
        await session.execute(delete(Feed).where(Feed.key.like(f"https://{prefix}.%")))
        await session.commit()


async def _run(n_users: int, n_items: int, timeout: float, keep: bool) -> int:
    import numpy as np

    from app.config import get_settings
    from app.services.metrics.queues import queue_report
    from app.workers.queue_metrics import _redis
    from app.workers.tasks.build_digest import build_digest_for_user

    prefix = f"lt{uuid.uuid4().hex[:8]}"
    slo = get_settings().digest_on_time_seconds
    try:
        user_ids = await _seed(prefix, n_users, n_items)
        due = time.time()
        for uid in user_ids:
            build_digest_for_user.apply_async((str(uid),), headers={"rp_due_at": due})
        print(f"Queued {len(user_ids)} builds; waiting up to {timeout:.0f}s")
        built = await _wait(user_ids, timeout)

        lateness = np.asarray([at.timestamp() - due for at in built.values()], dtype=float)
        missing = len(user_ids) - len(built)
        on_time = int((lateness <= slo).sum()) if lateness.size else 0
        result = {
            "users": len(user_ids),
            "built": len(built),
            "not_built_in_time": missing,
            "slo_seconds": slo,
            "on_time_ratio": round(on_time / len(user_ids), 4),
            "build_lateness_p50": round(float(np.percentile(lateness, 50)), 1)
            if lateness.size
            else None,
            "build_lateness_p95": round(float(np.percentile(lateness, 95)), 1)
            if lateness.size
            else None,
            "queues": queue_report(_redis(), hours=1),
        }
        print(json.dumps(result, indent=2, default=str))
        return 0 if result["on_time_ratio"] >= 0.99 else 1
    finally:
        if not keep:
            await _cleanup(prefix)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--items", type=int, default=60)
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--keep", action="store_true", help="keep the synthetic rows")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args.users, args.items, args.timeout, args.keep)))


if __name__ == "__main__":
    main()
