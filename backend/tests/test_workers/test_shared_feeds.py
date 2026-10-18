"""Shared feeds: one poll serves every subscriber (#161, #162, #163, #166)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

from app.models.content import ContentItem
from app.models.feed import Feed
from app.models.source import Source
from app.models.user import User
from app.services.ingestion.rss_parser import RawContentItem
from tests.conftest import TestingSessionLocal

FEED = "https://shared-feed.example.com/rss"


async def _subscribers(db_session, n: int) -> list[tuple[User, Source]]:
    out = []
    for i in range(n):
        user = User(
            email=f"sf{i}-{uuid.uuid4().hex[:6]}@example.com",
            hashed_password="x",
            onboarding_complete=True,
        )
        db_session.add(user)
        await db_session.flush()
        src = Source(
            user_id=user.id,
            url="https://shared-feed.example.com",
            feed_url=FEED,
            trust_weight=0.5 + 0.1 * i,
        )
        db_session.add(src)
        await db_session.flush()
        out.append((user, src))
    await db_session.commit()
    return out


async def _run(dispatch):
    from app.workers.tasks import ingest_feeds

    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.services.ingestion.dispatcher.dispatch_source", dispatch),
        patch("app.workers.tasks.compute_embeddings.compute_embedding_for_item.delay"),
    ):
        return await ingest_feeds._ingest_all_feeds_async()


@pytest.mark.asyncio
async def test_three_subscribers_cost_one_fetch_and_all_see_the_items(db_session):
    subs = await _subscribers(db_session, 3)
    calls: list[str] = []

    async def dispatch(target, session):
        calls.append(target.feed_url or target.url)
        return [
            RawContentItem(url=f"{FEED}/post-{i}", title=f"Post {i}", guid=f"g{i}")
            for i in range(2)
        ]

    result = await _run(dispatch)

    assert calls == [FEED]  # one HTTP poll for three users
    assert result["feeds_processed"] == 1 and result["new_items"] == 2
    async with TestingSessionLocal() as s:
        feed = (await s.execute(select(Feed))).scalar_one()
        sources = list((await s.execute(select(Source))).scalars())
        items = list((await s.execute(select(ContentItem))).scalars())
    assert {src.feed_id for src in sources} == {feed.id}
    assert all(item.feed_id == feed.id for item in items)
    # Poll state mirrored onto each subscriber's row (API/UI read it there).
    assert all(src.next_poll_at == feed.next_poll_at and src.last_fetched_at for src in sources)

    from app.services.digest.builder import build_digest

    for user, _ in subs:
        async with TestingSessionLocal() as s:
            digest = await build_digest(await s.get(User, user.id), s)
            await s.commit()
            assert digest.total_items == 2


@pytest.mark.asyncio
async def test_dead_feed_pauses_and_notifies_every_subscriber_once(db_session):
    await _subscribers(db_session, 2)

    async def gone(target, session):
        target.last_http_status = 410
        return []

    await _run(gone)

    async with TestingSessionLocal() as s:
        feed = (await s.execute(select(Feed))).scalar_one()
        sources = list((await s.execute(select(Source))).scalars())
    assert feed.is_active is False
    assert all(src.is_active is False and src.dead_notice_pending for src in sources)


@pytest.mark.asyncio
async def test_existing_reddit_sources_show_notice_once_and_are_paused(db_session, monkeypatch):
    """After the shutdown date, existing Reddit sources show the notice once and are
    paused without error-looping (#107)."""
    from app.services.ingestion import schedule

    monkeypatch.setattr(schedule, "REDDIT_RSS_END", datetime(2026, 1, 1, tzinfo=UTC))
    user = User(
        email="reddit_sub@example.com",
        hashed_password="x",
        email_verified_at=datetime.now(UTC),
        onboarding_complete=True,
    )
    db_session.add(user)
    await db_session.flush()

    src = Source(
        user_id=user.id,
        url="https://www.reddit.com/r/MachineLearning",
        feed_url="https://www.reddit.com/r/MachineLearning/.rss",
        is_active=True,
    )
    db_session.add(src)
    await db_session.commit()

    called = False

    async def fail_if_dispatched(target, session):
        nonlocal called
        called = True
        return []

    await _run(fail_if_dispatched)

    assert not called  # Reddit feeds are never fetched/error-looped

    async with TestingSessionLocal() as s:
        feed = (
            await s.execute(
                select(Feed).where(Feed.key == "https://www.reddit.com/r/MachineLearning/.rss")
            )
        ).scalar_one()
        source = (await s.execute(select(Source).where(Source.id == src.id))).scalar_one()

    assert feed.is_active is False
    assert feed.feed_status == "dead"
    assert "Unsupported: Reddit ended RSS on 13 Nov 2026" in (feed.last_error or "")
    assert source.is_active is False
    assert source.dead_notice_pending is True
    assert source.feed_status == "dead"
    assert "Unsupported: Reddit ended RSS on 13 Nov 2026" in (source.last_error or "")

    # Now verify delivery notices: notice is shown once, then cleared
    from app.services.digest.delivery import _clear_dead_notices, _pending_dead_sources

    async with TestingSessionLocal() as s:
        notices = await _pending_dead_sources(user.id, s)
        assert len(notices) == 1
        await _clear_dead_notices(user.id, s)
        await s.commit()

    async with TestingSessionLocal() as s:
        notices_second = await _pending_dead_sources(user.id, s)
        assert len(notices_second) == 0


@pytest.mark.asyncio
async def test_reddit_sources_keep_polling_until_the_shutdown_date(db_session, monkeypatch):
    """Before 13 Nov 2026 Reddit RSS still works: keep fetching it (#107)."""
    from app.services.ingestion import schedule

    monkeypatch.setattr(schedule, "REDDIT_RSS_END", datetime(2099, 1, 1, tzinfo=UTC))
    user = User(email="reddit_early@example.com", hashed_password="x", onboarding_complete=True)
    db_session.add(user)
    await db_session.flush()
    feed_url = "https://www.reddit.com/r/rust/.rss"
    db_session.add(Source(user_id=user.id, url="https://www.reddit.com/r/rust", feed_url=feed_url))
    await db_session.commit()
    calls: list[str] = []

    async def dispatch(target, session):
        calls.append(target.feed_url)
        return [RawContentItem(url=f"{feed_url}/post", title="Post", guid="p")]

    await _run(dispatch)

    assert calls == [feed_url]
    async with TestingSessionLocal() as s:
        feed = (await s.execute(select(Feed).where(Feed.key == feed_url))).scalar_one()
    assert feed.is_active is True and feed.feed_status != "dead"


@pytest.mark.asyncio
async def test_item_survives_deletion_of_the_subscriber_row_that_filed_it(db_session):
    subs = await _subscribers(db_session, 2)

    async def dispatch(target, session):
        return [RawContentItem(url=f"{FEED}/keep", title="Keep me", guid="k")]

    await _run(dispatch)
    async with TestingSessionLocal() as s:
        item = (await s.execute(select(ContentItem))).scalar_one()
        filer = next(src for _, src in subs if src.id == item.source_id)
        other_user = next(user for user, src in subs if src.id != filer.id)
        await s.delete(await s.get(Source, filer.id))
        await s.commit()

    from app.services.digest.builder import build_digest

    async with TestingSessionLocal() as s:
        digest = await build_digest(await s.get(User, other_user.id), s)
        await s.commit()
    assert digest.total_items == 1


@pytest.mark.asyncio
async def test_trust_comes_from_the_readers_own_subscription_via_feed_id(db_session):
    from app.services.ranking.ranker import rank

    (a, a_src), (b, b_src) = await _subscribers(db_session, 2)

    async def dispatch(target, session):
        return [RawContentItem(url=f"{FEED}/t", title="T", guid="t")]

    await _run(dispatch)
    async with TestingSessionLocal() as s:
        a_row, b_row = await s.get(Source, a_src.id), await s.get(Source, b_src.id)
        a_row.trust_weight, b_row.trust_weight = 0.9, 0.2
        item = (await s.execute(select(ContentItem))).scalar_one()
        item.source_id = None  # e.g. the filing row was deleted
        await s.commit()

    async with TestingSessionLocal() as s:
        item = (await s.execute(select(ContentItem))).scalar_one()
        scored = (await rank(await s.get(User, b.id), [item], s))[0]
    assert scored.features["source_trust"] == pytest.approx(0.2)


# ---------------------------------------------------------------- migration 0025

SYNC_BASE = os.environ.get(
    "DATABASE_SYNC_URL", "postgresql+psycopg2://readprism:readprism@localhost:5432/readprism_test"
)


@pytest.fixture
def db_at_0024():
    from alembic import command

    from app.migrate import _alembic_config

    name = f"rp_feeds_{uuid.uuid4().hex[:8]}"
    admin = create_engine(
        make_url(SYNC_BASE).set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as e:  # pragma: no cover
        pytest.skip(f"cannot create a scratch database: {e}")
    url = make_url(SYNC_BASE).set(database=name).render_as_string(hide_password=False)
    command.upgrade(_alembic_config(url), "0024")
    yield url
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def test_migration_merges_duplicate_subscriptions_into_one_feed(db_at_0024):
    from alembic import command

    from app.migrate import _alembic_config

    engine = create_engine(db_at_0024)
    users = [uuid.uuid4() for _ in range(3)]
    src = [uuid.uuid4() for _ in range(4)]
    with engine.begin() as conn:
        for i, uid in enumerate(users):
            conn.execute(
                text("INSERT INTO users (id, email, hashed_password) VALUES (:id, :e, 'x')"),
                {"id": uid, "e": f"m{i}@example.com"},
            )
        rows = [
            (src[0], users[0], "https://a.example", FEED, "rss", datetime(2026, 10, 1, tzinfo=UTC)),
            (src[1], users[1], "https://a.example", FEED, "rss", datetime(2026, 10, 9, tzinfo=UTC)),
            (src[2], users[2], "https://b.example", None, "rss", None),
            (src[3], users[2], "newsletter:x@example.com", None, "newsletter", None),
        ]
        for sid, uid, url, feed_url, kind, fetched in rows:
            conn.execute(
                text(
                    "INSERT INTO sources (id, user_id, url, feed_url, source_type, trust_weight, is_active, "
                    "fetch_error_count, last_fetched_at) VALUES (:id, :u, :url, :f, :k, 0.5, true, 0, :t)"
                ),
                {"id": sid, "u": uid, "url": url, "f": feed_url, "k": kind, "t": fetched},
            )
        conn.execute(
            text("INSERT INTO content_items (id, source_id, url, title) VALUES (:id, :s, :u, 't')"),
            {"id": uuid.uuid4(), "s": src[0], "u": f"{FEED}/1"},
        )

    command.upgrade(_alembic_config(db_at_0024), "0025")

    with engine.connect() as conn:
        feeds = conn.execute(text("SELECT key, last_fetched_at FROM feeds ORDER BY key")).all()
        feed_of = dict(conn.execute(text("SELECT id, feed_id FROM sources")).all())
        item_feed = conn.execute(text("SELECT feed_id FROM content_items")).scalar_one()
    assert [k for k, _ in feeds] == ["https://b.example", FEED]
    assert feeds[1][1].date().isoformat() == "2026-10-09"  # state from the latest fetcher
    assert feed_of[src[0]] == feed_of[src[1]] is not None
    assert feed_of[src[3]] is None  # newsletters stay private
    assert item_feed == feed_of[src[0]]

    command.downgrade(_alembic_config(db_at_0024), "0024")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('feeds')")).scalar() is None
    engine.dispose()


def test_dry_run_plan_counts_subscriptions_per_feed(db_at_0024):
    from app.feeds_plan import plan

    engine = create_engine(db_at_0024)
    with engine.begin() as conn:
        uid = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO users (id, email, hashed_password) VALUES (:id, 'p@example.com', 'x')"
            ),
            {"id": uid},
        )
        for url in (FEED, FEED, "https://solo.example/rss"):
            conn.execute(
                text(
                    "INSERT INTO sources (id, user_id, url, feed_url, source_type, trust_weight, is_active, fetch_error_count) "
                    "VALUES (:id, :u, 'https://x', :f, 'rss', 0.5, true, 0)"
                ),
                {"id": uuid.uuid4(), "u": uid, "f": url},
            )
    engine.dispose()
    assert plan(db_at_0024) == [(FEED, 2), ("https://solo.example/rss", 1)]
