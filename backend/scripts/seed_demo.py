"""Seed a demo persona so a fresh instance is instantly explorable (RL-03).

Offline: sources come from the starter packs, items are synthesized locally
(hash embeddings), a digest is built through the real builder.

    make demo   # or: cd backend && PYTHONPATH=. python3 scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select


async def main() -> None:
    from app.database import AsyncSessionLocal
    from app.models.content import ContentItem
    from app.models.source import Source
    from app.models.user import User
    from app.services.cold_start.starter_packs import list_starter_packs
    from app.services.digest.builder import build_digest

    password = secrets.token_urlsafe(12)
    async with AsyncSessionLocal() as session:
        email = "demo@readprism.local"
        existing = await session.execute(select(User).where(User.email == email))
        user = existing.scalar_one_or_none()
        if user is None:
            user = User(email=email, hashed_password=password, onboarding_complete=True)
            session.add(user)
            await session.flush()
        else:
            from app.api.auth import _hash_password

            user.hashed_password = _hash_password(password)
            await session.flush()

        # Idempotent: clear previous synthetic items (and their digests).
        from sqlalchemy import delete

        from app.models.digest import Digest, DigestItem

        old_items = (
            (
                await session.execute(
                    select(ContentItem).where(
                        ContentItem.url.like("https://demo.readprism.local/%")
                    )
                )
            )
            .scalars()
            .all()
        )
        if old_items:
            old_ids = [item.id for item in old_items]
            await session.execute(delete(DigestItem).where(DigestItem.content_item_id.in_(old_ids)))
            await session.execute(delete(ContentItem).where(ContentItem.id.in_(old_ids)))
            await session.execute(delete(Digest).where(Digest.user_id == user.id))
            await session.flush()

        # Sources: first feed of five starter packs; three synthetic items each.
        packs = list_starter_packs()[:5]
        existing_sources = {
            row[0]
            for row in (
                await session.execute(select(Source.url).where(Source.user_id == user.id))
            ).fetchall()
        }
        now = datetime.now(UTC)
        items = []
        for pack in packs:
            feed = pack.feeds[0]
            if feed["url"] not in existing_sources:
                src = Source(
                    user_id=user.id,
                    url=feed["url"],
                    name=feed["name"],
                    feed_url=feed["url"],
                    source_type="rss",
                    trust_weight=0.45,
                )
                session.add(src)
                await session.flush()
                existing_sources.add(feed["url"])
            else:
                src = (
                    await session.execute(
                        select(Source).where(Source.user_id == user.id, Source.url == feed["url"])
                    )
                ).scalar_one()
            for i in range(3):
                items.append(
                    ContentItem(
                        source_id=src.id,
                        url=f"https://demo.readprism.local/{pack.id}/{i}",
                        title=f"{pack.title} demo story {i + 1}",
                        summary_brief=f"A synthetic {pack.title.lower()} story for the demo digest.",
                        topic_clusters=[pack.id.replace("-", " ")],
                        fetched_at=now - timedelta(hours=i),
                        word_count=800,
                        reading_time_minutes=4,
                        embedding=_hash_vec(f"{pack.id}-{i}"),
                    )
                )
        session.add_all(items)
        await session.flush()
        digest = await build_digest(user, session)
        await session.commit()

        print("Demo persona seeded (RL-03):")
        print(f"  email:    {email}")
        print(f"  password: {password}")
        print(f"  digest:   {digest.total_items} items (in-app)")
        print("  log in at the frontend and open /digest")


def _hash_vec(seed: str, dim: int = 384) -> list[float]:
    """Deterministic unit vector — stable demo embeddings, no model needed."""
    raw = hashlib.sha256(seed.encode()).digest()
    vec = [(raw[i % len(raw)] / 255.0) - 0.5 for i in range(dim)]
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


if __name__ == "__main__":
    asyncio.run(main())
