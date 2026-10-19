"""The digest's candidate window (#313)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.content import ContentItem
from app.models.feed import Feed
from app.models.source import Source
from app.models.user import User
from app.services.digest.builder import _candidates


async def _world(db_session, feeds: int, per_feed: int):
    user = User(email=f"cw{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    now = datetime.now(UTC)
    feed_rows = []
    for f in range(feeds):
        key = f"https://cw{uuid.uuid4().hex[:6]}-{f}.example/rss"
        feed = Feed(key=key, url=key, feed_url=key)
        db_session.add(feed)
        await db_session.flush()
        db_session.add(Source(user_id=user.id, url=key, feed_url=key, feed_id=feed.id))
        feed_rows.append(feed)
        for i in range(per_feed):
            db_session.add(
                ContentItem(
                    feed_id=feed.id,
                    url=f"{key}/{i}",
                    title=f"feed {f} item {i}",
                    # Feed f's items are all older than feed f-1's newest, so a
                    # recency-only cut would drop the later feeds entirely.
                    fetched_at=now - timedelta(minutes=f * 60 + i),
                )
            )
    await db_session.flush()
    return user, feed_rows


@pytest.mark.asyncio
async def test_every_feeds_newest_items_compete_not_an_arbitrary_subset(db_session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "digest_per_source_cap", 2)
    monkeypatch.setattr(get_settings(), "digest_candidate_limit", 20)
    user, feeds = await _world(db_session, feeds=10, per_feed=8)  # 80 items, limit 20

    items = await _candidates(
        user, [], [f.id for f in feeds], datetime.now(UTC) - timedelta(days=1), db_session
    )

    assert len(items) == 20
    by_feed: dict = {}
    for item in items:
        by_feed.setdefault(item.feed_id, []).append(item.title)
    assert set(by_feed) == {f.id for f in feeds}  # every feed is represented
    for f, feed in enumerate(feeds):
        assert sorted(by_feed[feed.id]) == [
            f"feed {f} item 0",
            f"feed {f} item 1",
        ]  # its newest two
    assert [i.fetched_at for i in items] == sorted((i.fetched_at for i in items), reverse=True)


@pytest.mark.asyncio
async def test_unrankable_items_do_not_use_up_the_window(db_session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "digest_per_source_cap", 3)
    user, feeds = await _world(db_session, feeds=1, per_feed=6)
    newest = sorted(
        (
            await db_session.execute(
                ContentItem.__table__.select().where(ContentItem.feed_id == feeds[0].id)
            )
        ).all(),
        key=lambda r: r.fetched_at,
        reverse=True,
    )
    for row in newest[:2]:  # the two newest are listing pages, not articles
        item = await db_session.get(ContentItem, row.id)
        item.rankable = False
    await db_session.flush()

    items = await _candidates(
        user, [], [feeds[0].id], datetime.now(UTC) - timedelta(days=1), db_session
    )
    assert [i.title for i in items] == ["feed 0 item 2", "feed 0 item 3", "feed 0 item 4"]
