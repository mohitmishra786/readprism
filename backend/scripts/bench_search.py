#!/usr/bin/env python
"""Hybrid search latency at 100k items (#231).

Seeds one user's archive of ITEMS items across FEEDS feeds (titles and
summaries from a small vocabulary so full-text matches are realistic, and an
embedding tagged with the active model so the vector leg participates), then
calls GET /api/v1/search in process (ASGI, no network) for a mixed query set
and reports p50 / p95 / max. Budget: p95 < 300 ms.

Run against a throwaway database, never production:

    DATABASE_URL=postgresql+asyncpg://.../readprism_bench \\
      python scripts/bench_search.py --items 100000

Rows are tagged with a unique prefix and deleted afterwards (--keep to keep).
"""

from __future__ import annotations

import argparse
import asyncio
import random
import time
import uuid
from datetime import UTC, datetime, timedelta

WORDS = (
    "kernel scheduler latency cache vector index planner rust compiler tokenizer gradient "
    "dataset privacy cipher router packet storage replica consensus typography layout colour "
    "motion pricing churn hiring growth design garden climate ocean battery solar transit "
    "housing budget museum novel poetry postgres vacuum btree wal raft paxos kubernetes "
    "container sandbox wasm runtime allocator garbage collector benchmark profiler tracing"
).split()

QUERIES = [
    "postgres vacuum",
    "raft consensus",
    "rust compiler",
    "garbage collector",
    "kubernetes",
    "solar battery",
    "typography layout",
    "cache latency",
    "btree index",
    "wasm runtime",
    "privacy cipher",
    "pricing churn",
    "ocean climate",
    "tracing profiler",
    "scheduler",
    "how does the postgres planner choose an index",
    "consensus replica storage",
    "allocator benchmark",
    "transit housing budget",
    "museum poetry novel",
]


async def _seed(prefix: str, items: int, feeds: int) -> str:
    """Create the user, feeds and items; return an access token."""
    from sqlalchemy import insert, text

    from app.api.auth import _create_access_token
    from app.config import get_settings
    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem
    from app.models.feed import Feed
    from app.models.source import Source
    from app.models.user import User
    from app.services.embeddings.registry import active_spec, encode_with_spec

    s = get_settings()
    spec = active_spec(model=s.embedding_model, cutover=s.embedding_cutover_enabled)
    rng = random.Random(prefix)
    # One embedding per distinct title keeps seeding fast; items reuse them.
    titles = [" ".join(rng.sample(WORDS, 5)) for _ in range(400)]
    vectors = [list(map(float, encode_with_spec(t, spec))) for t in titles]
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        user = User(email=f"{prefix}@bench.invalid", hashed_password="x", onboarding_complete=True)
        session.add(user)
        feed_rows = [
            Feed(
                key=f"https://{prefix}-{f}.bench.invalid/rss",
                url=f"https://{prefix}-{f}.bench.invalid",
                feed_url=f"https://{prefix}-{f}.bench.invalid/rss",
            )
            for f in range(feeds)
        ]
        session.add_all(feed_rows)
        await session.flush()
        session.add_all(
            [
                Source(user_id=user.id, url=f.url, feed_url=f.feed_url, feed_id=f.id)
                for f in feed_rows
            ]
        )
        await session.flush()
        batch = []
        for i in range(items):
            t = rng.randrange(len(titles))
            batch.append(
                {
                    "id": uuid.uuid4(),
                    "feed_id": feed_rows[i % feeds].id,
                    "url": f"https://{prefix}-{i % feeds}.bench.invalid/{i}",
                    "title": titles[t].capitalize(),
                    "summary_brief": " ".join(rng.sample(WORDS, 12)).capitalize() + ".",
                    "summary_source": "extractive",
                    "topic_clusters": [titles[t].split()[0]],
                    "embedding": vectors[t],
                    "embedding_model": spec.name,
                    "embedding_dim": spec.dim,
                    "fetched_at": now - timedelta(minutes=i),
                    "word_count": 800,
                    "extraction_method": "feed",
                }
            )
            if len(batch) == 2000:
                await session.execute(insert(ContentItem), batch)
                batch = []
        if batch:
            await session.execute(insert(ContentItem), batch)
        await session.commit()
        await session.execute(text("ANALYZE content_items"))
        await session.commit()
        return _create_access_token(user.id)


async def _cleanup(prefix: str) -> None:
    from sqlalchemy import delete

    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem
    from app.models.feed import Feed
    from app.models.user import User

    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(ContentItem).where(ContentItem.url.like(f"https://{prefix}-%"))
        )
        await session.execute(delete(User).where(User.email == f"{prefix}@bench.invalid"))
        await session.execute(delete(Feed).where(Feed.key.like(f"https://{prefix}-%")))
        await session.commit()


def _pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p * (len(ordered) - 1))))]


async def _run(args: argparse.Namespace) -> None:
    import httpx

    from app.main import app

    prefix = f"srch{uuid.uuid4().hex[:6]}"
    start = time.perf_counter()
    token = await _seed(prefix, args.items, args.feeds)
    print(f"seeded {args.items} items in {args.feeds} feeds in {time.perf_counter() - start:.0f}s")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://bench") as client:
            for q in QUERIES[:3]:  # warm-up: model load, plan cache
                await client.get("/api/v1/search", params={"q": q}, headers=headers)
            times, hits = [], []
            for _ in range(args.rounds):
                for q in QUERIES:
                    t = time.perf_counter()
                    resp = await client.get("/api/v1/search", params={"q": q}, headers=headers)
                    times.append((time.perf_counter() - t) * 1000)
                    resp.raise_for_status()
                    hits.append(len(resp.json()["hits"]))
        print(
            f"search x{len(times)} over {args.items} items: p50 {_pct(times, 0.5):.0f} ms, "
            f"p95 {_pct(times, 0.95):.0f} ms, max {max(times):.0f} ms "
            f"(mean hits {sum(hits) / len(hits):.1f})"
        )
    finally:
        if not args.keep:
            await _cleanup(prefix)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--items", type=int, default=100_000)
    ap.add_argument("--feeds", type=int, default=300)
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--keep", action="store_true")
    asyncio.run(_run(ap.parse_args()))


if __name__ == "__main__":
    main()
