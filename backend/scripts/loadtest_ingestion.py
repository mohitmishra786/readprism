#!/usr/bin/env python
"""Load-test the PRS precompute path (audit 07-7).

The precompute is O(users x recent_items x 8 signals) with a pgvector kNN per
similarity signal — the first thing to fall over as users grow. This script
seeds synthetic users (with interest graphs) and content (with embeddings) into
a scratch schema, times scoring every (user, item) pair, and reports throughput
so you can check the 30-minute ingestion/precompute SLA on a given host before
launch.

    docker compose exec backend python scripts/loadtest_ingestion.py --users 50 --items 200

It writes to the configured database, tagging rows with a unique email/URL
prefix, and deletes them afterwards.
"""

from __future__ import annotations

import argparse
import asyncio
import time
import uuid

import numpy as np


def _rand_unit(dim: int = 384) -> list[float]:
    v = np.random.default_rng().standard_normal(dim).astype(np.float32)
    v /= np.linalg.norm(v) + 1e-8
    return v.tolist()


async def _run(n_users: int, n_items: int) -> None:
    from sqlalchemy import delete

    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem
    from app.models.interest_graph import InterestNode
    from app.models.user import User
    from app.services.ranking.scorer import compute_prs

    tag = f"loadtest-{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as session:
        print(f"Seeding {n_users} users + {n_items} items ({tag})...")
        users = []
        for i in range(n_users):
            u = User(email=f"{tag}-u{i}@example.com", hashed_password="x")
            session.add(u)
            users.append(u)
        await session.flush()
        for u in users:
            for t in range(3):  # 3 interest nodes each
                session.add(
                    InterestNode(
                        user_id=u.id, topic_label=f"t{t}", weight=0.6, topic_embedding=_rand_unit()
                    )
                )
        items = [
            ContentItem(url=f"https://{tag}.example/{i}", title=f"item {i}", embedding=_rand_unit())
            for i in range(n_items)
        ]
        session.add_all(items)
        await session.commit()

        pairs = n_users * n_items
        print(f"Scoring {pairs} (user, item) pairs...")
        start = time.perf_counter()
        for u in users:
            for item in items:
                await compute_prs(item, u, session)
        elapsed = time.perf_counter() - start

        rate = pairs / elapsed if elapsed else 0.0
        print(f"\nScored {pairs} pairs in {elapsed:.1f}s => {rate:.0f} pairs/sec")
        # Project the SLA: precompute for all pairs must fit the 30-min window.
        budget = 30 * 60
        max_pairs = int(rate * budget)
        print(f"At this rate, ~{max_pairs:,} pairs fit a 30-min precompute window.")
        print("(Compare against your expected active-users x recent-items.)")

        # Cleanup.
        print("\nCleaning up seeded rows...")
        await session.execute(delete(ContentItem).where(ContentItem.url.like(f"https://{tag}.%")))
        await session.execute(delete(User).where(User.email.like(f"{tag}-%")))
        await session.commit()
        print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load-test the PRS precompute path")
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--items", type=int, default=200)
    args = parser.parse_args()
    asyncio.run(_run(args.users, args.items))


if __name__ == "__main__":
    main()
