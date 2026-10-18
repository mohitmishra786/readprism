"""Raw telemetry retention (#224)."""

from __future__ import annotations

import fnmatch
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.models.content import ContentItem, UserContentInteraction
from app.models.digest import Digest, DigestImpression, ImpressionRollup
from app.models.user import User
from tests.conftest import TestingSessionLocal

NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)
OLD = NOW - timedelta(days=120)
RECENT = NOW - timedelta(days=5)


async def _seed(db_session):
    user = User(email=f"pt{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    digest = Digest(user_id=user.id)
    db_session.add(digest)
    items = [ContentItem(url=f"https://t.example/{i}", title=str(i)) for i in range(4)]
    db_session.add_all(items)
    await db_session.flush()
    for i, (when, viewed) in enumerate([(OLD, True), (OLD, False), (OLD, True), (RECENT, True)]):
        db_session.add(
            DigestImpression(
                user_id=user.id,
                content_item_id=items[i].id,
                digest_id=digest.id,
                section="lead",
                team="prs",
                viewed=viewed,
                features_json={"semantic": 0.4},
                shown_at=when,
            )
        )
    old_ix = UserContentInteraction(
        user_id=user.id,
        content_item_id=items[0].id,
        read_completion_pct=0.9,
        scroll_depth_pct=0.95,
        active_time_seconds=300,
        time_on_page_seconds=320,
        explicit_rating=1,
    )
    new_ix = UserContentInteraction(
        user_id=user.id,
        content_item_id=items[3].id,
        read_completion_pct=0.5,
        scroll_depth_pct=0.6,
        active_time_seconds=60,
    )
    db_session.add_all([old_ix, new_ix])
    await db_session.flush()
    old_ix.updated_at = OLD
    new_ix.updated_at = RECENT
    await db_session.commit()
    return old_ix.id, new_ix.id


async def _run():
    from app.workers.tasks.prune_telemetry import _prune_telemetry_async

    with patch("app.database.AsyncSessionLocal", TestingSessionLocal):
        return await _prune_telemetry_async(now=NOW)


@pytest.mark.asyncio
async def test_old_impressions_become_anonymous_counts(db_session):
    old_id, new_id = await _seed(db_session)

    first = await _run()
    second = await _run()  # idempotent: nothing left to fold in

    assert first["impressions_rolled_up"] == 3 and second["impressions_rolled_up"] == 0
    async with TestingSessionLocal() as s:
        remaining = list((await s.execute(select(DigestImpression))).scalars())
        rollups = list((await s.execute(select(ImpressionRollup))).scalars())
        old_ix = await s.get(UserContentInteraction, old_id)
        new_ix = await s.get(UserContentInteraction, new_id)
    assert [r.shown_at for r in remaining] == [RECENT]
    assert len(rollups) == 1
    r = rollups[0]
    assert (r.day, r.section, r.team, r.shown, r.viewed) == (OLD.date(), "lead", "prs", 3, 2)
    assert not hasattr(ImpressionRollup, "user_id")

    # Coarsened, but what ranking and the interest graph use is intact.
    assert old_ix.scroll_depth_pct is None and old_ix.active_time_seconds is None
    assert old_ix.read_completion_pct == 0.9 and old_ix.explicit_rating == 1
    assert old_ix.time_on_page_seconds == 320
    assert new_ix.scroll_depth_pct == 0.6 and new_ix.active_time_seconds == 60


@pytest.mark.asyncio
async def test_rollups_accumulate_across_runs(db_session):
    await _seed(db_session)
    await _run()
    async with TestingSessionLocal() as s:
        user = (await s.execute(select(User))).scalars().first()
        item = (await s.execute(select(ContentItem))).scalars().first()
        s.add(
            DigestImpression(
                user_id=user.id,
                content_item_id=item.id,
                section="lead",
                team="prs",
                viewed=True,
                shown_at=OLD,
            )
        )
        await s.commit()
    await _run()
    async with TestingSessionLocal() as s:
        shown = (await s.execute(select(func.sum(ImpressionRollup.shown)))).scalar()
    assert shown == 4


@pytest.mark.asyncio
async def test_disabled_when_retention_is_zero(db_session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "telemetry_raw_retention_days", 0)
    await _seed(db_session)
    assert (await _run()) == {"status": "disabled"}
    async with TestingSessionLocal() as s:
        assert (await s.execute(select(func.count()).select_from(DigestImpression))).scalar() == 4


def test_every_beat_task_is_routed_to_a_named_queue():
    from app.workers.celery_app import celery_app

    routes = celery_app.conf.task_routes or {}
    for name, entry in celery_app.conf.beat_schedule.items():
        task = entry["task"]
        matched = [r for pattern, r in routes.items() if fnmatch.fnmatch(task, pattern)]
        assert matched and matched[0].get("queue"), f"{name}: {task} has no queue route"
