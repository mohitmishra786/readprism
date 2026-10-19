"""Seed the demo persona so a fresh instance is instantly explorable (RL-03, #158).

Offline and reproducible. The persona, publications and ~30 articles in
app/data/demo/articles.json are fictional and written for ReadPrism (CC0;
nothing third-party). The script:

1. creates the persona with three interests and seven demo publications;
2. embeds every article with this instance's embedder (MiniLM on the
   standard image, the hash fallback on lite);
3. replays two weeks of reading (finished, skimmed, skipped, saved, rated)
   through the real interest-graph updater, so interests and source trust
   are learned, not hard-coded;
4. builds today's digest with the real builder.

    make demo   # or: cd backend && PYTHONPATH=. python3 scripts/seed_demo.py

Idempotent: re-running replaces the previous demo data.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import delete, select

DATA = Path(__file__).resolve().parents[1] / "app" / "data" / "demo" / "articles.json"
DEMO_HOST = "demo.readprism.local"

# How each kind of past read is recorded: completion, seconds on page, extras.
READS = {
    "finished": {"read_completion_pct": 0.96, "time_on_page_seconds": 260, "reached_end": True},
    "saved": {
        "read_completion_pct": 0.92,
        "time_on_page_seconds": 300,
        "reached_end": True,
        "saved": True,
    },
    "skimmed": {"read_completion_pct": 0.35, "time_on_page_seconds": 50},
    "skipped": {"read_completion_pct": 0.02, "time_on_page_seconds": 3, "skipped": True},
}


def feed_url(slug: str) -> str:
    return f"https://{slug}.{DEMO_HOST}/feed"


async def seed(session, *, password: str) -> dict:
    """Seed into `session`; returns a summary. Callers commit."""
    from app.api.auth import _hash_password
    from app.models.content import ContentItem, UserContentInteraction
    from app.models.digest import Digest
    from app.models.interest_graph import InterestNode
    from app.models.source import Source
    from app.models.user import User
    from app.services.digest.builder import build_digest
    from app.services.interest_graph.updater import update_from_interaction
    from app.utils.embeddings import get_embedding_service

    data = json.loads(DATA.read_text())
    persona = data["persona"]
    embedder = get_embedding_service()

    user = (
        await session.execute(select(User).where(User.email == persona["email"]))
    ).scalar_one_or_none()
    if user is None:
        user = User(email=persona["email"], hashed_password="", onboarding_complete=True)
        session.add(user)
    # bcrypt in both branches: a plaintext password can never log in.
    user.hashed_password = _hash_password(password)
    user.display_name = persona["name"]
    user.interest_text = persona["about"]
    user.onboarding_complete = True
    user.email_verified_at = user.email_verified_at or datetime.now(UTC)
    await session.flush()

    # Idempotent: drop the previous demo world for this persona.
    await session.execute(delete(Digest).where(Digest.user_id == user.id))
    await session.execute(
        delete(UserContentInteraction).where(UserContentInteraction.user_id == user.id)
    )
    await session.execute(delete(InterestNode).where(InterestNode.user_id == user.id))
    await session.execute(delete(Source).where(Source.user_id == user.id))
    await session.execute(
        delete(ContentItem).where(ContentItem.url.like(f"https://%.{DEMO_HOST}/%"))
    )
    await session.flush()

    for interest in persona["interests"]:
        session.add(
            InterestNode(
                user_id=user.id,
                topic_label=interest["topic"],
                topic_embedding=await embedder.encode_single(interest["topic"]),
                weight=interest["weight"],
            )
        )

    sources = {}
    for pub in data["publications"]:
        src = Source(
            user_id=user.id,
            url=f"https://{pub['slug']}.{DEMO_HOST}/",
            feed_url=feed_url(pub["slug"]),
            name=pub["name"],
            source_type="rss",
            trust_weight=0.5,
            initial_backfill_done=True,
        )
        session.add(src)
        sources[pub["slug"]] = (src, pub["topic"])
    await session.flush()

    now = datetime.now(UTC)
    history: list[tuple[ContentItem, dict]] = []
    fresh = 0
    for index, art in enumerate(data["articles"]):
        src, topic = sources[art["pub"]]
        body = "\n\n".join(art["body"])
        when = (
            now - timedelta(days=art["days_ago"], hours=index % 5)
            if "days_ago" in art
            else now - timedelta(hours=art["age_hours"])
        )
        words = len(body.split())
        item = ContentItem(
            source_id=src.id,
            url=f"https://{art['pub']}.{DEMO_HOST}/{index:02d}",
            title=art["title"],
            author=art["author"],
            summary_brief=art["summary"],
            summary_source="extractive",
            full_text=body,
            topic_clusters=[topic],
            embedding=await embedder.encode_single(f"{art['title']}. {art['summary']} {body}"),
            embedding_model=embedder.model_name,
            embedding_dim=embedder.dimension,
            word_count=words,
            reading_time_minutes=max(1, round(words / 220)),
            content_depth_score=0.7 if words > 120 else 0.5,
            has_citations=False,
            extraction_method="feed",
            published_at=when,
            fetched_at=when,
        )
        session.add(item)
        if "read" in art:
            history.append((item, art))
        else:
            fresh += 1
    await session.flush()

    # Two weeks of reading, learned through the real updater.
    for item, art in history:
        record = dict(READS[art["read"]])
        if "rating" in art:
            record["explicit_rating"] = art["rating"]
        opened = item.fetched_at + timedelta(hours=2)
        ix = UserContentInteraction(
            user_id=user.id,
            content_item_id=item.id,
            opened_at=None if record.get("skipped") else opened,
            saved_at=opened if record.get("saved") else None,
            saved_read_at=opened if record.get("saved") else None,
            **record,
        )
        session.add(ix)
        await session.flush()
        await update_from_interaction(ix, item, session)
    await session.flush()

    digest = await build_digest(user, session)
    return {
        "email": persona["email"],
        "digest_items": digest.total_items,
        "history": len(history),
        "fresh": fresh,
        "digest_id": digest.id,
    }


async def main() -> None:
    from app.database import AsyncSessionLocal

    password = secrets.token_urlsafe(12)
    async with AsyncSessionLocal() as session:
        summary = await seed(session, password=password)
        await session.commit()
    print("Demo persona seeded (RL-03, #158):")
    print(f"  email:    {summary['email']}")
    print(f"  password: {password}")
    print(
        f"  reading:  {summary['history']} articles read over two weeks; "
        f"{summary['fresh']} new today"
    )
    print(f"  digest:   {summary['digest_items']} items (in-app)")
    print("  log in at the frontend and open /digest")


if __name__ == "__main__":
    asyncio.run(main())
