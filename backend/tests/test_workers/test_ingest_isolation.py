"""Ingest isolation (#100): one source's URL collision must not abort the run.

`content_items.url` is unique across the instance, while dedup inside
`dispatch_source` only looks at the same source. These tests reproduce the
collisions that used to raise PendingRollbackError and discard every source's
items on every run.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.content import ContentItem
from app.models.creator import Creator
from app.models.source import Source
from app.models.user import User
from app.services.ingestion.rss_parser import RawContentItem
from tests.conftest import TestingSessionLocal


def _user(email: str) -> User:
    return User(id=uuid.uuid4(), email=email, hashed_password="x", onboarding_complete=True)


def _fake_dispatch(by_host: dict[str, list[RawContentItem]]):
    async def dispatch(source, session):
        for host, items in by_host.items():
            if host in source.url:
                return list(items)
        return []

    return dispatch


async def _run_ingest(dispatch) -> dict:
    from app.workers.tasks import ingest_feeds

    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.services.ingestion.dispatcher.dispatch_source", dispatch),
        patch("app.workers.tasks.compute_embeddings.compute_embedding_for_item.delay"),
    ):
        return await ingest_feeds._ingest_all_feeds_async()


@pytest.mark.asyncio
async def test_two_users_same_feed_does_not_discard_other_sources(db_session):
    a, b, c = _user("a@example.com"), _user("b@example.com"), _user("c@example.com")
    db_session.add_all([a, b, c])
    await db_session.flush()
    db_session.add_all(
        [
            Source(
                user_id=a.id,
                url="https://blog.example.com",
                feed_url="https://blog.example.com/feed",
            ),
            Source(
                user_id=b.id,
                url="https://blog.example.com",
                feed_url="https://blog.example.com/feed",
            ),
            Source(
                user_id=c.id,
                url="https://other.example.org",
                feed_url="https://other.example.org/feed",
            ),
        ]
    )
    await db_session.commit()

    dispatch = _fake_dispatch(
        {
            "blog.example.com": [
                RawContentItem(url="https://blog.example.com/post-1", title="Post 1", guid="p1")
            ],
            "other.example.org": [
                RawContentItem(url="https://other.example.org/x", title="Other", guid="x1")
            ],
        }
    )
    result = await _run_ingest(dispatch)

    async with TestingSessionLocal() as s:
        urls = {row[0] for row in (await s.execute(select(ContentItem.url))).all()}
        next_polls = [row[0] for row in (await s.execute(select(Source.next_poll_at))).all()]
    assert urls == {"https://blog.example.com/post-1", "https://other.example.org/x"}
    assert result["new_items"] == 2
    assert all(next_poll is not None for next_poll in next_polls)


@pytest.mark.asyncio
async def test_extension_saved_url_later_in_feed_keeps_ingesting(db_session):
    user = _user("solo@example.com")
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        ContentItem(
            url="https://blog.example.com/post-1",
            title="Saved",
            origin="extension",
            owner_user_id=user.id,
        )
    )
    db_session.add_all(
        [
            Source(
                user_id=user.id,
                url="https://blog.example.com",
                feed_url="https://blog.example.com/feed",
            ),
            Source(
                user_id=user.id,
                url="https://other.example.org",
                feed_url="https://other.example.org/feed",
            ),
        ]
    )
    await db_session.commit()

    for run in range(3):
        # Make everything due again, as successive beat ticks would. Polling
        # state lives on the shared feeds since #162.
        from app.models.feed import Feed

        async with TestingSessionLocal() as s:
            for row in [
                *(await s.execute(select(Source))).scalars(),
                *(await s.execute(select(Feed))).scalars(),
            ]:
                row.next_poll_at = None
            await s.commit()
        dispatch = _fake_dispatch(
            {
                "blog.example.com": [
                    RawContentItem(url="https://blog.example.com/post-1", title="Post 1", guid="p1")
                ],
                "other.example.org": [
                    RawContentItem(
                        url=f"https://other.example.org/{run}", title=f"Other {run}", guid=f"o{run}"
                    )
                ],
            }
        )
        await _run_ingest(dispatch)

    async with TestingSessionLocal() as s:
        urls = {row[0] for row in (await s.execute(select(ContentItem.url))).all()}
        sources = list((await s.execute(select(Source))).scalars())
    assert {f"https://other.example.org/{run}" for run in range(3)} <= urls
    assert all(src.next_poll_at is not None for src in sources)


@pytest.mark.asyncio
async def test_failing_source_records_backoff_and_others_continue(db_session):
    user = _user("fail@example.com")
    db_session.add(user)
    await db_session.flush()
    db_session.add_all(
        [
            Source(
                user_id=user.id,
                url="https://broken.example.com",
                feed_url="https://broken.example.com/f",
            ),
            Source(
                user_id=user.id,
                url="https://fine.example.org",
                feed_url="https://fine.example.org/f",
            ),
        ]
    )
    await db_session.commit()

    async def dispatch(source, session):
        if "broken" in source.url:
            raise RuntimeError("feed exploded")
        return [RawContentItem(url="https://fine.example.org/1", title="Fine", guid="f1")]

    await _run_ingest(dispatch)

    async with TestingSessionLocal() as s:
        broken = (await s.execute(select(Source).where(Source.url.contains("broken")))).scalar_one()
        urls = {row[0] for row in (await s.execute(select(ContentItem.url))).all()}
    assert "https://fine.example.org/1" in urls
    assert broken.last_error and "feed exploded" in broken.last_error
    assert broken.next_poll_at is not None


@pytest.mark.asyncio
async def test_creator_reingest_inserts_nothing_new_and_does_not_raise(db_session):
    user = _user("creator@example.com")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Creator(user_id=user.id, display_name="Someone"))
    await db_session.commit()

    async def fetch(creator, session):
        return [RawContentItem(url="https://video.example.com/1", title="Video 1")]

    from app.workers.tasks import ingest_feeds

    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.services.creator.tracker.fetch_creator_content", fetch),
        patch("app.workers.tasks.compute_embeddings.compute_embedding_for_item.delay") as delay,
    ):
        first = await ingest_feeds._ingest_creator_feeds_async()
        second = await ingest_feeds._ingest_creator_feeds_async()

    assert first["new_items"] == 1
    assert second["new_items"] == 0
    assert delay.call_count == 1  # embeddings only for genuinely new rows


def test_one_failed_embedding_enqueue_does_not_stop_the_rest():
    from app.workers.tasks import ingest_feeds

    ids = [uuid.uuid4() for _ in range(3)]
    calls: list[str] = []

    def delay(item_id):
        calls.append(item_id)
        if item_id == str(ids[0]):
            raise ConnectionError("broker down")

    with patch("app.workers.tasks.compute_embeddings.compute_embedding_for_item.delay", delay):
        ingest_feeds._enqueue_embeddings(ids)
    assert calls == [str(i) for i in ids]


@pytest.mark.asyncio
async def test_failed_rollback_does_not_end_the_run(db_session):
    user = _user("rb@example.com")
    db_session.add(user)
    await db_session.flush()
    db_session.add_all(
        [
            Source(
                user_id=user.id,
                url="https://dead.example.com",
                feed_url="https://dead.example.com/f",
            ),
            Source(
                user_id=user.id, url="https://ok.example.org", feed_url="https://ok.example.org/f"
            ),
        ]
    )
    await db_session.commit()

    async def dispatch(source, session):
        if "dead" in source.url:
            raise RuntimeError("connection reset")
        return [RawContentItem(url="https://ok.example.org/1", title="Ok", guid="o1")]

    real_rollback = TestingSessionLocal.class_.rollback

    async def flaky_rollback(self):
        await real_rollback(self)
        raise RuntimeError("rollback on a dead connection")

    with patch.object(TestingSessionLocal.class_, "rollback", flaky_rollback):
        await _run_ingest(dispatch)

    async with TestingSessionLocal() as s:
        urls = {row[0] for row in (await s.execute(select(ContentItem.url))).all()}
    assert "https://ok.example.org/1" in urls


@pytest.mark.asyncio
async def test_repair_requeues_committed_items_without_embeddings(db_session):
    from datetime import UTC, datetime, timedelta

    from app.workers.tasks.compute_embeddings import _repair_missing_embeddings_async

    now = datetime.now(UTC)
    stuck = ContentItem(
        url="https://r.example/stuck", title="s", fetched_at=now - timedelta(hours=1)
    )
    fresh = ContentItem(
        url="https://r.example/fresh", title="f", fetched_at=now - timedelta(minutes=2)
    )
    old = ContentItem(url="https://r.example/old", title="o", fetched_at=now - timedelta(days=10))
    db_session.add_all([stuck, fresh, old])
    await db_session.commit()
    seen: set[str] = set()

    async def nx(key, value, ttl_seconds):
        if key in seen:
            return False
        seen.add(key)
        return True

    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.utils.cache.cache_set_nx", nx),
        patch("app.workers.tasks.compute_embeddings.compute_embedding_for_item.delay") as delay,
    ):
        first = await _repair_missing_embeddings_async(now=now)
        second = await _repair_missing_embeddings_async(now=now)
    delay.assert_called_once_with(str(stuck.id))
    assert first["queued"] == 1 and second["queued"] == 0
