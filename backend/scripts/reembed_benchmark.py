#!/usr/bin/env python
"""Benchmark for online embedding model re-embed (#244).

Seeds N synthetic items in a scratch database, runs the online re-embed in
batches of 200 with a fast fake encoder, and issues concurrent search queries
every second to verify 0 query failures during migration.

Usage:
    cd backend && APP_ENV=development python scripts/reembed_benchmark.py [--items 50000]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base
from app.models.content import ContentItem
from app.services.embeddings.reembed import reembed_batch
from app.services.embeddings.registry import (
    BGE_SPEC,
    MINILM,
    MINILM_DIM,
    VERSION,
)


class FakeFastEncoder:
    """Fast deterministic encoder for benchmarking pipeline throughput without torch CPU overhead."""

    def __init__(self, dim: int = 384) -> None:
        self.dimension = dim
        self._fixed_vector = [0.05] * dim

    async def encode_batch_cached(self, texts: list[str]) -> list[list[float]]:
        return [self._fixed_vector for _ in texts]

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [self._fixed_vector for _ in texts]


async def seed_synthetic_items(
    session_factory: async_sessionmaker[AsyncSession],
    n: int,
    batch_size: int = 1000,
) -> None:
    print(f"Seeding {n} synthetic items with {MINILM}...")
    start = time.perf_counter()
    now = datetime.now(UTC)

    for offset in range(0, n, batch_size):
        chunk_size = min(batch_size, n - offset)
        rows = [
            {
                "id": uuid.uuid4(),
                "url": f"https://benchmark.example.com/item/{offset + i}",
                "title": f"Benchmark synthetic article {offset + i} about storage engines",
                "summary_brief": f"Brief summary for item {offset + i}",
                "full_text": f"Article text for synthetic item {offset + i}. " * 8,
                "embedding": [0.01 * ((offset + i) % 50)] * MINILM_DIM,
                "embedding_model": MINILM,
                "embedding_dim": MINILM_DIM,
                "embedding_version": VERSION,
                "fetched_at": now,
            }
            for i in range(chunk_size)
        ]
        async with session_factory() as session:
            await session.execute(insert(ContentItem).values(rows))
            await session.commit()
        print(
            f"  seeded {offset + chunk_size}/{n} items ({((offset + chunk_size) / n) * 100:.1f}%)"
        )

    elapsed = time.perf_counter() - start
    print(f"Seeding completed in {elapsed:.2f}s ({n / elapsed:.1f} rows/s)")


async def query_worker(
    session_factory: async_sessionmaker[AsyncSession],
    stop_event: asyncio.Event,
    stats: dict[str, int],
) -> None:
    """Issues queries continuously every second during migration and records errors."""
    while not stop_event.is_set():
        try:
            async with session_factory() as session:
                # Query recent items filtering by active or legacy model
                result = await session.execute(
                    select(ContentItem.id, ContentItem.title, ContentItem.embedding_model)
                    .where(ContentItem.embedding.is_not(None))
                    .order_by(ContentItem.id.desc())
                    .limit(10)
                )
                rows = result.all()
                if len(rows) > 0:
                    stats["queries_succeeded"] += 1
                else:
                    stats["queries_failed"] += 1
        except Exception as e:
            stats["queries_failed"] += 1
            print(f"Query failure: {e}", file=sys.stderr)

        await asyncio.sleep(1.0)


async def run_benchmark(
    db_url: str,
    n_items: int,
    batch_size: int,
) -> dict[str, float | int]:
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    # Initialize tables
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Seed items
    await seed_synthetic_items(session_factory, n=n_items)

    target_spec = BGE_SPEC
    encoder = FakeFastEncoder(dim=target_spec.dim)

    print(f"\nStarting online re-embed benchmark to {target_spec.name}...")
    print(f"Batch size: {batch_size}, Total items: {n_items}")

    query_stats = {"queries_succeeded": 0, "queries_failed": 0}
    stop_queries = asyncio.Event()
    query_task = asyncio.create_task(query_worker(session_factory, stop_queries, query_stats))

    start_time = time.perf_counter()
    cursor = None
    total_reembedded = 0
    batches_run = 0

    while True:
        async with session_factory() as session:
            res = await reembed_batch(
                session=session,
                active=target_spec,
                batch_size=batch_size,
                cursor=cursor,
                encoder=encoder,
            )
        total_reembedded += res["reembedded"]
        cursor = res["next_cursor"]
        batches_run += 1

        if res["done"]:
            break

        if batches_run % 25 == 0:
            elapsed_so_far = time.perf_counter() - start_time
            rate = total_reembedded / elapsed_so_far if elapsed_so_far > 0 else 0
            print(
                f"  progress: {total_reembedded}/{n_items} items ({total_reembedded / n_items * 100:.1f}%) "
                f"- {rate:.1f} rows/s (queries: {query_stats['queries_succeeded']} ok, {query_stats['queries_failed']} failed)"
            )

    wall_time = time.perf_counter() - start_time
    stop_queries.set()
    await query_task

    # Verify counts in DB
    async with session_factory() as session:
        count_target = await session.scalar(
            select(func.count(ContentItem.id)).where(
                ContentItem.embedding_model == target_spec.name
            )
        )
        count_old = await session.scalar(
            select(func.count(ContentItem.id)).where(
                ContentItem.embedding_model != target_spec.name
            )
        )

    rows_per_second = total_reembedded / wall_time if wall_time > 0 else 0
    time_per_10k = (10000 / rows_per_second) if rows_per_second > 0 else 0

    print("\n" + "=" * 60)
    print("RE-EMBED BENCHMARK RESULTS")
    print("=" * 60)
    print(f"Total items re-embedded:  {total_reembedded}")
    print(f"Target model rows in DB:  {count_target}")
    print(f"Old model rows remaining: {count_old}")
    print(f"Total batches processed:  {batches_run} (batch size {batch_size})")
    print(f"Wall time:                {wall_time:.2f} seconds")
    print(f"Throughput:               {rows_per_second:.1f} rows/second")
    print(f"Estimated time per 10k:   {time_per_10k:.2f} seconds ({time_per_10k / 60:.2f} minutes)")
    print(f"Concurrent search queries:{query_stats['queries_succeeded']}")
    print(f"Failed search queries:    {query_stats['queries_failed']}")
    print("=" * 60)

    await engine.dispose()
    return {
        "items": total_reembedded,
        "wall_time": round(wall_time, 2),
        "rows_per_second": round(rows_per_second, 1),
        "queries_succeeded": query_stats["queries_succeeded"],
        "queries_failed": query_stats["queries_failed"],
        "time_per_10k_sec": round(time_per_10k, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Online embedding model re-embed benchmark")
    parser.add_argument(
        "--items", type=int, default=50000, help="Number of items to seed and re-embed"
    )
    parser.add_argument("--batch-size", type=int, default=200, help="Batch size per transaction")
    parser.add_argument(
        "--db-url",
        type=str,
        default=os.environ.get(
            "BENCHMARK_DATABASE_URL",
            "postgresql+asyncpg://readprism:readprism@localhost:5432/readprism_benchmark",
        ),
        help="Postgres async connection URL",
    )
    args = parser.parse_args()

    from app.config import get_settings

    s = get_settings()
    if "redis://redis:" in s.redis_url:
        import socket

        try:
            socket.gethostbyname("redis")
        except socket.gaierror:
            s.redis_url = s.redis_url.replace("redis://redis:", "redis://localhost:")

    asyncio.run(run_benchmark(args.db_url, args.items, args.batch_size))


if __name__ == "__main__":
    main()
