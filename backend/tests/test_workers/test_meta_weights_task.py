"""Weight-training task scoping and debounce (#104)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.content import ContentItem, UserContentInteraction
from app.models.digest import Digest
from app.models.user import User
from tests.conftest import TestingSessionLocal


def _user(email: str) -> User:
    return User(id=uuid.uuid4(), email=email, hashed_password="x", onboarding_complete=True)


@pytest.mark.asyncio
async def test_task_trains_only_on_the_users_own_digests(db_session):
    """The weight task learns from this user's settled digests only (#104, #154)."""
    from sqlalchemy import select

    from app.models.digest import DigestImpression
    from app.models.meta_weights import UserMetaWeights
    from app.workers.tasks import update_interest_graph as task

    a, b = _user("ma@example.com"), _user("mb@example.com")
    db_session.add_all([a, b])
    await db_session.flush()
    old = datetime.now(UTC) - timedelta(days=2)
    for owner in (a, b):
        digest = Digest(user_id=owner.id, generated_at=old)
        db_session.add(digest)
        await db_session.flush()
        for completion in (0.95, 0.05):
            item = ContentItem(url=f"https://t.example/{uuid.uuid4().hex}", title="t")
            db_session.add(item)
            await db_session.flush()
            db_session.add(
                DigestImpression(
                    user_id=owner.id,
                    content_item_id=item.id,
                    digest_id=digest.id,
                    features_json={"content_quality": completion},
                    viewed=True,
                )
            )
            if owner is b:
                db_session.add(
                    UserContentInteraction(
                        user_id=b.id,
                        content_item_id=item.id,
                        read_completion_pct=completion,
                        opened_at=old,
                    )
                )
    await db_session.commit()

    with patch("app.database.AsyncSessionLocal", TestingSessionLocal):
        result_a = await task._update_meta_weights_async(a.id)
        result_b = await task._update_meta_weights_async(b.id)

    assert result_a["pairs"] == 0  # B's reading never trains A
    assert result_b["pairs"] == 1
    rows = {r.user_id: r for r in (await db_session.execute(select(UserMetaWeights))).scalars()}
    assert rows[b.id].pairs_seen == 1 and rows[a.id].pairs_seen == 0


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
