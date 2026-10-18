"""Discovery pool on a single-user instance (#141)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.interest_graph import InterestNode
from app.models.source import Source
from app.models.user import User
from app.services.cold_start.starter_packs import StarterPack
from app.services.discovery.pool import refresh_for_user
from app.services.ingestion.rss_parser import RawContentItem

ARTICLE = "word " * 400


def _page(url: str, **kw) -> RawContentItem:
    return RawContentItem(url=url, title=f"Page {url}", full_text=ARTICLE, word_count=400, **kw)


async def _reader(db_session) -> tuple[User, Source]:
    user = User(
        email=f"dp{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="x",
        onboarding_complete=True,
        digest_max_items=8,
    )
    db_session.add(user)
    await db_session.flush()
    src = Source(user_id=user.id, url="https://mine.example", feed_url="https://mine.example/f")
    db_session.add(src)
    await db_session.flush()
    return user, src


async def _finished(db_session, user, src, text: str, *, days_ago: float = 1, pct: float = 0.9):
    item = ContentItem(
        source_id=src.id,
        url=f"https://mine.example/{uuid.uuid4().hex}",
        title="Read",
        full_text=text,
        fetched_at=datetime.now(UTC),
    )
    db_session.add(item)
    await db_session.flush()
    db_session.add(
        UserContentInteraction(
            user_id=user.id,
            content_item_id=item.id,
            read_completion_pct=pct,
            opened_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )
    await db_session.flush()
    return item


@pytest.mark.asyncio
async def test_outbound_links_become_labelled_discovery_items(db_session):
    user, src = await _reader(db_session)
    await _finished(
        db_session,
        user,
        src,
        "See https://elsewhere.example/deep-dive and https://twitter.com/x/status/1 "
        "and https://mine.example/other and https://short.example/stub",
    )
    await _finished(db_session, user, src, "Old https://stale.example/a", days_ago=10)
    await _finished(db_session, user, src, "Skimmed https://skimmed.example/a", pct=0.2)
    await db_session.commit()
    fetched: list[str] = []

    async def scrape(url):
        fetched.append(url)
        if "short" in url:
            return RawContentItem(url=url, title="stub", full_text="tiny", word_count=3)
        return _page(url)

    with patch("app.services.cold_start.starter_packs.list_starter_packs", return_value=[]):
        ids = await refresh_for_user(user.id, db_session, scrape=scrape)
    await db_session.commit()

    assert fetched == ["https://elsewhere.example/deep-dive", "https://short.example/stub"]
    item = (
        await db_session.execute(select(ContentItem).where(ContentItem.id.in_(ids)))
    ).scalar_one()
    assert item.origin == "discovery" and item.owner_user_id is None and item.source_id is None
    assert item.discovered_via == "a link in mine.example"

    # A second run fetches nothing new: the URL is already stored.
    fetched.clear()
    with patch("app.services.cold_start.starter_packs.list_starter_packs", return_value=[]):
        assert await refresh_for_user(user.id, db_session, scrape=scrape) == []
    assert fetched == ["https://short.example/stub"]


@pytest.mark.asyncio
async def test_starter_pack_fallback_matches_interests_and_respects_the_cap(db_session):
    user, src = await _reader(db_session)
    db_session.add(InterestNode(user_id=user.id, topic_label="Rust programming", weight=0.9))
    await db_session.commit()
    packs = [
        StarterPack(
            id="rust",
            title="Rust",
            feeds=[
                {
                    "name": "followed",
                    "url": "https://mine.example",
                    "feed_url": "https://mine.example/f",
                },
                *(
                    {
                        "name": f"r{i}",
                        "url": f"https://r{i}.example",
                        "feed_url": f"https://r{i}.example/f",
                    }
                    for i in range(6)
                ),
            ],
        ),
        StarterPack(
            id="cooking",
            title="Cooking",
            feeds=[{"name": "c", "url": "https://c.example", "feed_url": "https://c.example/f"}],
        ),
    ]
    cache: dict = {}
    calls: list[str] = []

    async def fetch_feed(url):
        calls.append(url)
        now = datetime.now(UTC)
        return SimpleNamespace(
            items=[
                RawContentItem(url=f"{url}/old", title="old", published_at=now - timedelta(days=3)),
                RawContentItem(url=f"{url}/new", title="new", published_at=now),
            ]
        )

    with patch("app.services.cold_start.starter_packs.list_starter_packs", return_value=packs):
        ids = await refresh_for_user(
            user.id, db_session, scrape=None, fetch_feed=fetch_feed, feed_cache=cache, limit=4
        )
    await db_session.commit()

    assert len(ids) == 4
    assert "https://mine.example/f" not in calls and "https://c.example/f" not in calls
    rows = list(
        (await db_session.execute(select(ContentItem).where(ContentItem.id.in_(ids)))).scalars()
    )
    assert all(r.url.endswith("/new") and r.discovered_via == "the Rust starter pack" for r in rows)
    assert set(cache) == set(calls)  # later users in the same run reuse these fetches


@pytest.mark.asyncio
async def test_single_user_digest_includes_a_discovery_item(db_session, monkeypatch):
    from app.config import get_settings
    from app.services.digest.builder import build_digest

    monkeypatch.setattr(get_settings(), "digest_per_source_cap", 50)
    user, src = await _reader(db_session)
    now = datetime.now(UTC)
    for i in range(8):
        db_session.add(
            ContentItem(
                source_id=src.id,
                url=f"https://mine.example/p{i}",
                title=f"Mine {i}",
                topic_clusters=[f"t{i}"],
                summary_brief="ok",
                fetched_at=now,
            )
        )
    await _finished(db_session, user, src, "Go read https://elsewhere.example/gem")
    await db_session.commit()

    async def scrape(url):
        return _page(url)

    with patch("app.services.cold_start.starter_packs.list_starter_packs", return_value=[]):
        await refresh_for_user(user.id, db_session, scrape=scrape)
    await db_session.commit()
    assert (await db_session.execute(select(User).where(User.id != user.id))).first() is None

    with patch("app.services.summarization.groq_client.GroqSummarizer", side_effect=Exception):
        digest = await build_digest(user, db_session)
    await db_session.commit()

    from app.models.digest import DigestItem

    rows = list(
        (
            await db_session.execute(
                select(DigestItem, ContentItem)
                .join(ContentItem, ContentItem.id == DigestItem.content_item_id)
                .where(DigestItem.digest_id == digest.id)
            )
        ).all()
    )
    found = [(d, c) for d, c in rows if c.origin == "discovery"]
    assert found, [c.url for _, c in rows]
    d, c = found[0]
    assert c.url == "https://elsewhere.example/gem"
    assert (d.signal_breakdown or {}).get("discovered_via") == "a link in mine.example"
