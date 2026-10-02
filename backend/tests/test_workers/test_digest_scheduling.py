"""Digest scheduling (UX-03): frequency slots, DST, dedupe, learned send time."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.digest import Digest
from app.models.user import User
from app.workers.tasks.build_digest import (
    _dedupe_window,
    _is_digest_time_for_user,
    _learn_send_times_async,
    _should_deliver_email,
)


def _user(
    tz: str = "UTC",
    preferred_hour: int = 7,
    frequency: str = "daily",
    send_time_locked: bool = False,
) -> MagicMock:
    user = MagicMock()
    user.timezone = tz
    user.digest_time_morning = time(preferred_hour, 0)
    user.digest_frequency = frequency
    user.send_time_locked = send_time_locked
    return user


def _session_factory(db_session):
    """Stand-in for AsyncSessionLocal that yields the test session."""

    @asynccontextmanager
    async def _factory():
        yield db_session

    return _factory


def test_dedupe_window_matches_frequency():
    assert _dedupe_window("daily") == timedelta(hours=12)
    assert _dedupe_window("twice_daily") == timedelta(hours=6)
    assert _dedupe_window("weekly") == timedelta(hours=84)


def test_morning_slot_matches_in_window():
    import zoneinfo

    ny = zoneinfo.ZoneInfo("America/New_York")
    user = _user(tz="America/New_York", preferred_hour=8)
    assert _is_digest_time_for_user(user, now=datetime(2026, 6, 15, 8, 5, tzinfo=ny)) is True
    assert _is_digest_time_for_user(user, now=datetime(2026, 6, 15, 6, 0, tzinfo=ny)) is False


def test_dst_spring_forward_and_fall_back():
    """The local 8:00 window still matches on the US DST transition days."""
    import zoneinfo

    ny = zoneinfo.ZoneInfo("America/New_York")
    user = _user(tz="America/New_York", preferred_hour=8)
    # 2026-03-08: clocks jump 2:00 -> 3:00. 8:05 local exists and must match.
    assert _is_digest_time_for_user(user, now=datetime(2026, 3, 8, 8, 5, tzinfo=ny)) is True
    # 2026-11-01: clocks fall back 2:00 -> 1:00. 8:05 local again.
    assert _is_digest_time_for_user(user, now=datetime(2026, 11, 1, 8, 5, tzinfo=ny)) is True
    # Midnight wrap: preferred 23:55, now 00:05 (10 minutes past) is inside.
    night = _user(tz="UTC", preferred_hour=23)
    night.digest_time_morning = time(23, 55)
    assert _is_digest_time_for_user(night, now=datetime(2026, 6, 15, 0, 5, tzinfo=UTC)) is True


def test_twice_daily_matches_evening_slot():
    import zoneinfo

    ny = zoneinfo.ZoneInfo("America/New_York")
    user = _user(tz="America/New_York", preferred_hour=8, frequency="twice_daily")
    # Evening slot is 20:00 local.
    assert _is_digest_time_for_user(user, now=datetime(2026, 6, 15, 20, 10, tzinfo=ny)) is True
    # A daily user does NOT get the evening slot.
    daily = _user(tz="America/New_York", preferred_hour=8, frequency="daily")
    assert _is_digest_time_for_user(daily, now=datetime(2026, 6, 15, 20, 10, tzinfo=ny)) is False


def _digest(total: int) -> SimpleNamespace:
    return SimpleNamespace(total_items=total)


def test_email_skipped_below_min_items(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "digest_min_items", 3)
    user = _user(frequency="daily")
    assert _should_deliver_email(user, _digest(5)) is True
    assert _should_deliver_email(user, _digest(2)) is False  # nothing worth reading
    in_app_only = _user(frequency="in_app_only")
    assert _should_deliver_email(in_app_only, _digest(10)) is False


@pytest.mark.asyncio
async def test_duplicate_build_inside_window_is_skipped(db_session):
    """A digest generated inside the dedupe window blocks a second send."""
    from app.workers.tasks import build_digest as mod

    user = User(email="dedupe@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        Digest(
            user_id=user.id,
            generated_at=datetime.now(UTC) - timedelta(hours=1),
            delivery_method="in_app",
            section_counts={},
            total_items=5,
        )
    )
    await db_session.commit()

    with (
        patch("app.database.AsyncSessionLocal", _session_factory(db_session)),
        patch("app.services.digest.builder.build_digest") as mock_build,
    ):
        result = await mod._build_digest_async(user.id)

    assert result["status"] == "duplicate_skipped"
    assert result["digest_id"] is not None
    mock_build.assert_not_called()  # no second digest, no second email


@pytest.mark.asyncio
async def test_learn_send_time_moves_to_open_peak(db_session):
    """The weekly job moves unlocked users to their peak open hour."""
    user = User(
        email="night-owl@example.com",
        hashed_password="x",
        send_time_locked=False,
        onboarding_complete=True,
        digest_time_morning=time(7, 0),
    )
    locked = User(
        email="locked@example.com",
        hashed_password="x",
        send_time_locked=True,
        onboarding_complete=True,
        digest_time_morning=time(7, 0),
    )
    db_session.add_all([user, locked])
    await db_session.flush()

    def _content(seq: int) -> uuid.UUID:
        row = ContentItem(
            id=uuid.uuid4(),
            url=f"https://sched.example/{seq}",
            title=f"sched-{seq}",
            fetched_at=datetime.now(UTC),
        )
        db_session.add(row)
        return row.id

    # The owl opens everything around 21:00 UTC over 40 days (>= min opens).
    seq = 0
    for day in range(40):
        for _ in range(2):
            db_session.add(
                UserContentInteraction(
                    user_id=user.id,
                    content_item_id=_content(seq),
                    opened_at=datetime(2026, 9, 1, 21, 10, tzinfo=UTC) + timedelta(days=day),
                )
            )
            seq += 1
    # The locked user opens at 22:00 — must stay at 7:00.
    for day in range(40):
        db_session.add(
            UserContentInteraction(
                user_id=locked.id,
                content_item_id=_content(seq),
                opened_at=datetime(2026, 9, 1, 22, 10, tzinfo=UTC) + timedelta(days=day),
            )
        )
        seq += 1
    await db_session.flush()

    from app.workers.tasks import build_digest as mod

    with patch("app.database.AsyncSessionLocal", _session_factory(db_session)):
        result = await mod._learn_send_times_async()

    await db_session.refresh(user)
    await db_session.refresh(locked)
    assert user.digest_time_morning == time(21, 0)
    assert locked.digest_time_morning == time(7, 0)  # explicit choice kept
    assert result["send_times_updated"] == 1


@pytest.mark.asyncio
async def test_concurrent_build_skipped_when_lock_held(db_session, monkeypatch):
    """A second build while the per-user lock is held returns without building."""
    from app.workers.tasks import build_digest as mod

    user = User(email="locked-build@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.commit()

    async def _no_lock(*args, **kwargs):
        return False

    monkeypatch.setattr("app.utils.cache.cache_set_nx", _no_lock)
    with patch("app.services.digest.builder.build_digest") as mock_build:
        result = await mod._build_digest_async(user.id)
    assert result["status"] == "build_in_progress"
    mock_build.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_path_recovers_lost_delivery(db_session, monkeypatch):
    """An undelivered digest inside the window gets its delivery re-enqueued."""
    from app.workers.tasks import build_digest as mod

    user = User(email="recover@example.com", hashed_password="x", digest_frequency="daily")
    db_session.add(user)
    await db_session.flush()
    digest = Digest(
        user_id=user.id,
        generated_at=datetime.now(UTC) - timedelta(hours=1),
        delivery_method="in_app",
        section_counts={},
        total_items=5,
    )  # delivered_at is None: the build died before enqueueing
    db_session.add(digest)
    await db_session.commit()

    holds = {"n": 0}

    async def _lock(*args, **kwargs):
        holds["n"] += 1
        return True

    monkeypatch.setattr("app.utils.cache.cache_set_nx", _lock)

    async def _unlock(*args, **kwargs):
        return True

    monkeypatch.setattr("app.utils.cache.cache_delete", _unlock)

    with (
        patch("app.database.AsyncSessionLocal", _session_factory(db_session)),
        patch("app.workers.tasks.deliver_digest.deliver_digest_task") as mock_delay,
    ):
        result = await mod._build_digest_async(user.id)

    assert result["status"] == "duplicate_skipped"
    mock_delay.delay.assert_called_once_with(str(digest.id))
