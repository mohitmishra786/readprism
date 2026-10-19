"""Learning and delivery workers (#145): the paths the earlier suites skipped."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.creator import Creator, CreatorPlatform
from app.models.creator_trust import CreatorTopicTrust
from app.models.digest import Digest
from app.models.user import User
from app.services.interest_graph.updater import _compute_signal_strength
from tests.conftest import TestingSessionLocal


def _ix(**kw) -> SimpleNamespace:
    base = {
        "explicit_rating": None,
        "read_completion_pct": None,
        "time_on_page_seconds": None,
        "saved": False,
        "saved_read_at": None,
        "was_suggested": False,
    }
    return SimpleNamespace(**{**base, **kw})


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        ({"explicit_rating": 1}, 1.0),
        ({"explicit_rating": -1}, -0.8),
        ({"saved": True, "saved_read_at": datetime.now(UTC)}, 0.9),
        ({"saved": True}, 0.1),
        ({"time_on_page_seconds": 3, "read_completion_pct": 0.02}, -0.2),  # a bounce
        ({"read_completion_pct": 0.9, "time_on_page_seconds": 200}, 0.8),
        ({"read_completion_pct": 0.9, "time_on_page_seconds": 200, "was_suggested": True}, 1.2),
        ({"read_completion_pct": 0.6, "time_on_page_seconds": 90}, 0.4),
        ({"read_completion_pct": 0.3, "time_on_page_seconds": 60}, 0.0),
    ],
)
def test_signal_strength_table(kw, expected):
    """Explicit ratings beat saves, which beat reading depth; a bounce is negative."""
    assert _compute_signal_strength(_ix(**kw)) == pytest.approx(expected)


@pytest.mark.asyncio
async def test_reading_a_creators_post_builds_per_topic_trust(db_session):
    from app.services.interest_graph.updater import update_from_interaction

    user = User(email=f"ct{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    creator = Creator(user_id=user.id, display_name="Writer")
    db_session.add(creator)
    await db_session.flush()
    platform = CreatorPlatform(
        creator_id=creator.id, platform="substack", platform_url="https://w.substack.com"
    )
    db_session.add(platform)
    await db_session.flush()
    item = ContentItem(
        url=f"https://w.substack.com/p/{uuid.uuid4().hex}",
        title="T",
        creator_platform_id=platform.id,
        topic_clusters=["compilers", "rust"],
    )
    db_session.add(item)
    await db_session.flush()
    ix = UserContentInteraction(
        user_id=user.id, content_item_id=item.id, read_completion_pct=0.95, time_on_page_seconds=300
    )
    db_session.add(ix)
    await db_session.flush()

    await update_from_interaction(ix, item, db_session)
    await db_session.commit()

    trust = {
        t.topic_label: t
        for t in (
            await db_session.execute(
                select(CreatorTopicTrust).where(CreatorTopicTrust.creator_id == creator.id)
            )
        ).scalars()
    }
    assert set(trust) == {"compilers", "rust"}
    assert all(t.trust_weight > 0.5 and t.interaction_count == 1 for t in trust.values())


@pytest.mark.asyncio
async def test_deliver_task_paths(db_session):
    from app.workers.tasks.deliver_digest import _deliver_digest_async

    with patch("app.database.AsyncSessionLocal", TestingSessionLocal):
        assert (await _deliver_digest_async(uuid.uuid4()))["status"] == "digest_not_found"

        user = User(
            email=f"dl{uuid.uuid4().hex[:6]}@example.com",
            hashed_password="x",
            email_verified_at=datetime.now(UTC),
        )
        db_session.add(user)
        await db_session.flush()
        digest = Digest(user_id=user.id, total_items=0)
        db_session.add(digest)
        await db_session.commit()

        with patch("app.services.digest.delivery.send_email", AsyncMock(return_value=True)) as send:
            result = await _deliver_digest_async(digest.id)
        assert result["status"] == "ok"
        send.assert_awaited_once()
        assert send.await_args.kwargs["to"] == user.email

    async with TestingSessionLocal() as s:
        assert (await s.get(Digest, digest.id)).delivered_at is not None


@pytest.mark.asyncio
async def test_discovery_task_isolates_a_failing_user(db_session):
    from app.workers.tasks.discovery import _refresh_all

    ok_user = User(
        email=f"d1{uuid.uuid4().hex[:6]}@example.com", hashed_password="x", onboarding_complete=True
    )
    bad_user = User(
        email=f"d2{uuid.uuid4().hex[:6]}@example.com", hashed_password="x", onboarding_complete=True
    )
    db_session.add_all([ok_user, bad_user])
    await db_session.commit()
    new_id = uuid.uuid4()

    async def refresh(user_id, session, feed_cache):
        if user_id == bad_user.id:
            raise RuntimeError("fetch exploded")
        return [new_id]

    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.services.discovery.pool.refresh_for_user", refresh),
        patch("app.workers.tasks.ingest_feeds._enqueue_embeddings") as enqueue,
    ):
        result = await _refresh_all()

    assert result == {"users": 2, "new_items": 1}
    enqueue.assert_called_once_with([new_id])


@pytest.mark.asyncio
async def test_beat_heartbeat_writes_a_short_lived_key():
    from app.workers.tasks.heartbeat import HEARTBEAT_KEY, HEARTBEAT_TTL_SECONDS, _write_heartbeat

    with patch("app.utils.cache.cache_set", AsyncMock(return_value=True)) as cache_set:
        result = await _write_heartbeat()
    key, value = cache_set.await_args.args
    assert key == HEARTBEAT_KEY and value == result["heartbeat"]
    assert cache_set.await_args.kwargs["ttl_seconds"] == HEARTBEAT_TTL_SECONDS
