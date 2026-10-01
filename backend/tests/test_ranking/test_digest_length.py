"""Digest length personalization (UX-02): EMA formula, clamp, explicit lock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.content import ContentItem, UserContentInteraction
from app.models.digest import Digest, DigestImpression
from app.models.user import User
from app.services.digest.builder import _learn_digest_length
from app.services.digest.length import ema_opened_per_digest, target_digest_length


def test_ema_weights_recent_digests_more():
    counts = [2.0, 2.0, 2.0, 10.0]  # a recent burst of opens
    ema = ema_opened_per_digest(counts)
    assert ema > 2.0
    assert ema < 10.0
    # Alpha=0.3: 2 -> 2 -> 2 -> 2*0.7 + 10*0.3 = 4.4
    assert ema == pytest.approx(4.4)


def test_ema_empty_returns_none():
    assert ema_opened_per_digest([]) is None


def test_target_length_formula_and_clamp():
    # 1.25 * 4.4 = 5.5 -> 6 (within bounds)
    assert target_digest_length(4.4, current=12, locked=False) == 6
    # Floor: 1.25 * 1 = 1.25 -> clamped to 5
    assert target_digest_length(1.0, current=12, locked=False) == 5
    # Cap: 1.25 * 40 = 50 -> clamped to 30
    assert target_digest_length(40.0, current=12, locked=False) == 30


def test_locked_or_missing_history_keeps_current():
    assert target_digest_length(4.4, current=12, locked=True) == 12
    assert target_digest_length(None, current=12, locked=False) == 12


async def _seed_digest_with_opens(db_session, user, *, opened: int, total: int, days_ago: int):
    digest = Digest(
        user_id=user.id,
        generated_at=datetime.now(UTC) - timedelta(days=days_ago),
        delivery_method="in_app",
        section_counts={},
        total_items=total,
    )
    db_session.add(digest)
    await db_session.flush()
    for i in range(total):
        item = ContentItem(
            url=f"https://len.example/{days_ago}-{i}",
            title=f"len-{days_ago}-{i}",
            fetched_at=datetime.now(UTC),
        )
        db_session.add(item)
        await db_session.flush()
        db_session.add(
            DigestImpression(
                user_id=user.id,
                content_item_id=item.id,
                digest_id=digest.id,
                section="lead",
                position=i,
                score=0.5,
            )
        )
        if i < opened:
            db_session.add(
                UserContentInteraction(
                    user_id=user.id,
                    content_item_id=item.id,
                    opened_at=datetime.now(UTC),
                )
            )
    await db_session.flush()


@pytest.mark.asyncio
async def test_learner_updates_length_from_open_history(db_session):
    user = User(email="len-auto@example.com", hashed_password="x", digest_max_items=12)
    db_session.add(user)
    await db_session.flush()

    # Three past digests; the user opened 2, 2, then 10 items.
    await _seed_digest_with_opens(db_session, user, opened=2, total=12, days_ago=3)
    await _seed_digest_with_opens(db_session, user, opened=2, total=12, days_ago=2)
    await _seed_digest_with_opens(db_session, user, opened=10, total=12, days_ago=1)
    await db_session.commit()

    await _learn_digest_length(user, db_session)
    # EMA(2, 2, 10) = 4.4 -> round(1.25 * 4.4) = 6
    assert user.digest_max_items == 6


@pytest.mark.asyncio
async def test_locked_length_is_never_clobbered(db_session):
    user = User(
        email="len-locked@example.com",
        hashed_password="x",
        digest_max_items=20,
        digest_length_locked=True,
    )
    db_session.add(user)
    await db_session.flush()
    await _seed_digest_with_opens(db_session, user, opened=2, total=12, days_ago=1)
    await db_session.commit()

    await _learn_digest_length(user, db_session)
    assert user.digest_max_items == 20


@pytest.mark.asyncio
async def test_no_digest_history_means_no_change(db_session):
    user = User(email="len-new@example.com", hashed_password="x", digest_max_items=12)
    db_session.add(user)
    await db_session.commit()

    await _learn_digest_length(user, db_session)
    assert user.digest_max_items == 12
