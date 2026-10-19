#!/usr/bin/env python
"""Digest build time at 1,000 candidates and 1,000 users (#192).

Seeds a synthetic world (no network): FEEDS feeds with ITEMS_PER_FEED fresh
items each, every item with a 384-d embedding, and USERS onboarded users who
follow every feed and have a handful of interest nodes. Then measures, in
process (no Celery):

1. the ranker on all candidates for one user (rank(), repeated), and
2. a full build_digest() for every user, sequentially: p50 / p95 / total.

Run against a throwaway database, never production:

    DATABASE_URL=postgresql+asyncpg://.../readprism_bench \\
      python scripts/bench_digest_build.py --users 1000

Rows are tagged with a unique prefix and deleted afterwards (--keep to keep).
"""

from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta

DIM = 384


def _vec(rng: random.Random, centre: list[float] | None = None) -> list[float]:
    raw = [rng.gauss(0, 1) for _ in range(DIM)]
    if centre is not None:
        raw = [c * 3 + r for c, r in zip(centre, raw, strict=True)]
    norm = sum(x * x for x in raw) ** 0.5
    return [x / norm for x in raw]


async def _seed(prefix: str, feeds: int, per_feed: int, users: int) -> list[uuid.UUID]:
    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem
    from app.models.feed import Feed
    from app.models.interest_graph import InterestNode
    from app.models.source import Source
    from app.models.user import User

    rng = random.Random(prefix)
    topics = [_vec(rng) for _ in range(24)]  # topic centres items cluster around
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        feed_rows = []
        for f in range(feeds):
            key = f"https://{prefix}-{f}.bench.invalid/rss"
            feed = Feed(key=key, url=key, feed_url=key)
            session.add(feed)
            feed_rows.append(feed)
        await session.flush()
        for f, feed in enumerate(feed_rows):
            for i in range(per_feed):
                t = rng.randrange(len(topics))
                session.add(
                    ContentItem(
                        feed_id=feed.id,
                        url=f"{feed.key}/{i}",
                        title=f"Item {f}-{i} about topic {t}",
                        summary_brief=f"Synthetic item {f}-{i}.",
                        summary_source="extractive",
                        topic_clusters=[f"topic-{t}"],
                        embedding=_vec(rng, topics[t]),
                        fetched_at=now - timedelta(minutes=rng.randrange(600)),
                        word_count=rng.choice([300, 900, 2400]),
                        extraction_method="feed",
                    )
                )
        await session.flush()
        ids: list[uuid.UUID] = []
        for u in range(users):
            user = User(
                email=f"{prefix}-{u}@bench.invalid",
                hashed_password="x",
                onboarding_complete=True,
                digest_max_items=20,
            )
            session.add(user)
            await session.flush()
            for feed in feed_rows:
                session.add(
                    Source(user_id=user.id, url=feed.key, feed_url=feed.key, feed_id=feed.id)
                )
            for t in rng.sample(range(len(topics)), 6):
                session.add(
                    InterestNode(
                        user_id=user.id,
                        topic_label=f"topic-{t}",
                        topic_embedding=topics[t],
                        weight=rng.uniform(0.4, 0.9),
                    )
                )
            ids.append(user.id)
            if u % 100 == 99:
                await session.flush()
        await session.commit()
    return ids


async def _cleanup(prefix: str) -> None:
    from sqlalchemy import delete

    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem
    from app.models.feed import Feed
    from app.models.user import User

    async with AsyncSessionLocal() as session:
        await session.execute(delete(User).where(User.email.like(f"{prefix}-%@bench.invalid")))
        await session.execute(
            delete(ContentItem).where(ContentItem.url.like(f"https://{prefix}-%"))
        )
        await session.execute(delete(Feed).where(Feed.key.like(f"https://{prefix}-%")))
        await session.commit()


def _pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p * (len(ordered) - 1))))]


async def _run(args: argparse.Namespace) -> None:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem
    from app.models.user import User
    from app.services.digest.builder import build_digest
    from app.services.ranking.ranker import rank

    prefix = f"bench{uuid.uuid4().hex[:6]}"
    t0 = time.perf_counter()
    user_ids = await _seed(prefix, args.feeds, args.per_feed, args.users)
    print(
        f"seeded {args.feeds * args.per_feed} items, {args.users} users "
        f"in {time.perf_counter() - t0:.1f}s"
    )
    try:
        # 1. Ranker on every candidate, for one user.
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_ids[0])
            items = list(
                (
                    await session.execute(
                        select(ContentItem).where(ContentItem.url.like(f"https://{prefix}-%"))
                    )
                ).scalars()
            )
            times = []
            for _ in range(args.repeat):
                start = time.perf_counter()
                scored = await rank(user, items, session)
                times.append(time.perf_counter() - start)
            print(
                f"rank() on {len(items)} candidates: p50 {statistics.median(times) * 1000:.0f} ms, "
                f"max {max(times) * 1000:.0f} ms ({len(scored)} scored, {args.repeat} runs)"
            )

        # 2. Full digest build for every user.
        builds = []
        wall = time.perf_counter()
        for uid in user_ids:
            async with AsyncSessionLocal() as session:
                user = await session.get(User, uid)
                start = time.perf_counter()
                digest = await build_digest(user, session)
                await session.commit()
                builds.append(time.perf_counter() - start)
        total = time.perf_counter() - wall
        print(
            f"build_digest x{len(builds)}: p50 {_pct(builds, 0.5) * 1000:.0f} ms, "
            f"p95 {_pct(builds, 0.95) * 1000:.0f} ms, max {max(builds) * 1000:.0f} ms, "
            f"total {total:.1f}s (one process, sequential; last digest "
            f"{digest.total_items} items)"
        )
    finally:
        if not args.keep:
            await _cleanup(prefix)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--users", type=int, default=1000)
    ap.add_argument("--feeds", type=int, default=200)
    ap.add_argument("--per-feed", type=int, default=5)
    ap.add_argument("--repeat", type=int, default=5)
    ap.add_argument("--keep", action="store_true")
    asyncio.run(_run(ap.parse_args()))


if __name__ == "__main__":
    main()
