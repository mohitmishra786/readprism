"""Weight-training task scoping and debounce (#104)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.content import ContentItem, UserContentInteraction
from app.models.digest import Digest, DigestItem
from app.models.user import User
from tests.conftest import TestingSessionLocal


def _user(email: str) -> User:
    return User(id=uuid.uuid4(), email=email, hashed_password="x", onboarding_complete=True)


async def _captured_pairs(user_id: uuid.UUID) -> list[tuple]:
    from app.workers.tasks import update_interest_graph as task

    captured: dict = {}

    async def fake_update(uid, pairs, session):
        captured["pairs"] = pairs

    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.services.ranking.meta_weights.update_meta_weights", fake_update),
    ):
        await task._update_meta_weights_async(user_id)
    return captured["pairs"]


@pytest.mark.asyncio
async def test_training_pairs_come_only_from_the_users_own_digests(db_session):
    a, b = _user("ma@example.com"), _user("mb@example.com")
    db_session.add_all([a, b])
    await db_session.flush()
    shared = ContentItem(url="https://shared.example.com/1", title="Shared")
    db_session.add(shared)
    await db_session.flush()
    digest_a, digest_b = Digest(user_id=a.id), Digest(user_id=b.id)
    db_session.add_all([digest_a, digest_b])
    await db_session.flush()
    db_session.add_all(
        [
            DigestItem(
                digest_id=digest_a.id,
                content_item_id=shared.id,
                position=0,
                section="lead",
                prs_score=0.5,
                signal_breakdown={"semantic": 0.9},
            ),
            DigestItem(
                digest_id=digest_b.id,
                content_item_id=shared.id,
                position=0,
                section="lead",
                prs_score=0.5,
                signal_breakdown={"semantic": 0.1},
            ),
            UserContentInteraction(
                user_id=a.id, content_item_id=shared.id, read_completion_pct=1.0
            ),
        ]
    )
    await db_session.commit()

    pairs = await _captured_pairs(a.id)

    assert len(pairs) == 1
    digest_item, interaction = pairs[0]
    assert digest_item.digest_id == digest_a.id
    assert interaction.user_id == a.id


@pytest.mark.asyncio
async def test_training_window_takes_the_most_recent_digests(db_session, monkeypatch):
    from app.workers.tasks import update_interest_graph as task

    monkeypatch.setattr(task, "META_TRAINING_WINDOW", 2)
    user = _user("recent@example.com")
    db_session.add(user)
    await db_session.flush()
    now = datetime.now(UTC)
    digest_ids = []
    for age_days in (10, 5, 0):
        item = ContentItem(url=f"https://recent.example.com/{age_days}", title=f"Item {age_days}")
        db_session.add(item)
        await db_session.flush()
        digest = Digest(user_id=user.id, generated_at=now - timedelta(days=age_days))
        db_session.add(digest)
        await db_session.flush()
        digest_ids.append(digest.id)
        db_session.add_all(
            [
                DigestItem(
                    digest_id=digest.id,
                    content_item_id=item.id,
                    position=0,
                    section="lead",
                    prs_score=0.5,
                    signal_breakdown={"semantic": 0.5},
                ),
                UserContentInteraction(
                    user_id=user.id, content_item_id=item.id, read_completion_pct=0.9
                ),
            ]
        )
    await db_session.commit()

    pairs = await _captured_pairs(user.id)

    assert [p[0].digest_id for p in pairs] == [digest_ids[2], digest_ids[1]]


@pytest.mark.asyncio
async def test_burst_of_interactions_schedules_one_update(monkeypatch):
    from app.workers.tasks import update_interest_graph as task

    store: set[str] = set()

    async def fake_set_nx(key, value, ttl_seconds):
        if key in store:
            return False
        store.add(key)
        return True

    monkeypatch.setattr("app.utils.cache.cache_set_nx", fake_set_nx)
    user_id = uuid.uuid4()
    with patch.object(task.update_meta_weights_task, "apply_async") as apply_async:
        results = [await task._enqueue_meta_weights_update(user_id) for _ in range(10)]

    assert results.count(True) == 1
    apply_async.assert_called_once()
    assert apply_async.call_args.kwargs["countdown"] == task.META_UPDATE_DELAY_SECONDS
