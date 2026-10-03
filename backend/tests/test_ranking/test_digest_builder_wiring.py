"""End-to-end wiring of the digest builder (UX-01).

Covers the assembly rules the section unit tests cannot see:
- the serendipity picks (and only those / origin=discovery) fill the discovery
  section — a low-scoring *followed* item must not be mislabeled as discovery
- every digest item gets a digest_impressions row
- exploration slots are applied only behind RANKING_EXPLORATION_ENABLED and
  record their softmax propensity
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.content import ContentItem
from app.models.digest import Digest, DigestImpression, DigestItem
from app.models.source import Source
from app.models.user import User
from app.services.digest.builder import build_digest


def _vec(*first_values: float) -> list[float]:
    v = [0.0] * 384
    for i, val in enumerate(first_values):
        v[i] = val
    return v


def _item(
    source_id,
    url: str,
    title: str,
    *,
    origin: str = "followed",
    reading_time: int = 10,
    topics: list[str] | None = None,
) -> ContentItem:
    return ContentItem(
        source_id=source_id,
        url=url,
        title=title,
        origin=origin,
        reading_time_minutes=reading_time,
        fetched_at=datetime.now(UTC),
        rankable=True,
        topic_clusters=topics or [],
        word_count=800,
    )


async def _seed(db_session, *, followed_per_source: int = 3):
    user = User(email="digest-owner@example.com", hashed_password="x")
    other = User(email="discovery-owner@example.com", hashed_password="x")
    db_session.add_all([user, other])
    await db_session.flush()

    src_a = Source(user_id=user.id, url="https://a.example/feed", name="A")
    src_b = Source(user_id=other.id, url="https://b.example/feed", name="B")
    db_session.add_all([src_a, src_b])
    await db_session.flush()

    now = datetime.now(UTC)
    for i in range(followed_per_source):
        db_session.add(
            _item(
                src_a.id,
                f"https://a.example/{i}",
                f"followed-{i}",
                topics=[f"a{i}"],
                reading_time=10,
            )
        )
    # Public item on a source the user does not follow, from the discovery pool.
    db_session.add(
        _item(
            src_b.id,
            "https://b.example/discovery",
            "public-discovery",
            origin="discovery",
            topics=["b0"],
        )
    )
    await db_session.commit()
    return user, src_a


@pytest.mark.asyncio
async def test_discovery_section_holds_only_discovery_items(db_session):
    user, _src_a = await _seed(db_session)

    digest = await build_digest(user, db_session)
    await db_session.commit()

    items = list(
        (
            await db_session.execute(select(DigestItem).where(DigestItem.digest_id == digest.id))
        ).scalars()
    )
    assert items, "digest should contain items"

    by_section: dict[str, list[DigestItem]] = {}
    for di in items:
        by_section.setdefault(di.section, []).append(di)

    # The origin=discovery item is the only discovery-section row.
    discovery_titles = []
    for di in by_section.get("discovery", []):
        row = (
            await db_session.execute(
                select(ContentItem).where(ContentItem.id == di.content_item_id)
            )
        ).scalar_one()
        discovery_titles.append(row.title)
        assert row.origin == "discovery"
    assert discovery_titles == ["public-discovery"]

    # Followed items (even low-PRS ones) never land in discovery.
    titles = {di.content_item_id for di in by_section.get("lead", [])}
    titles |= {di.content_item_id for di in by_section.get("deep_reads", [])}
    followeds = (
        (
            await db_session.execute(
                select(ContentItem).where(
                    ContentItem.id.in_(titles), ContentItem.origin == "followed"
                )
            )
        )
        .scalars()
        .all()
    )
    assert followeds, "followed items should be placed in lead/deep_reads"

    # Every digest item has an impression row with the default propensity.
    impressions = list(
        (
            await db_session.execute(
                select(DigestImpression).where(DigestImpression.digest_id == digest.id)
            )
        ).scalars()
    )
    assert len(impressions) == len(items)
    assert all(imp.propensity == 1.0 for imp in impressions)
    assert all(imp.exploration is False for imp in impressions)  # flag off by default


@pytest.mark.asyncio
async def test_exploration_slots_flag_and_record_propensity(db_session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "ranking_exploration_enabled", True)
    user, _src_a = await _seed(db_session)
    # A second followed source: 3 + 3 followed (per-source cap 3) + 1 discovery
    # = 7 placed items, enough for the exploration pool (positions 6-40).
    other_src = Source(user_id=user.id, url="https://c.example/feed", name="C")
    db_session.add(other_src)
    await db_session.flush()
    for i in range(3):
        db_session.add(
            _item(
                other_src.id,
                f"https://c.example/{i}",
                f"followed-c{i}",
                topics=[f"c{i}"],
                reading_time=10,
            )
        )
    await db_session.commit()

    digest = await build_digest(user, db_session)
    await db_session.commit()

    impressions = list(
        (
            await db_session.execute(
                select(DigestImpression).where(DigestImpression.digest_id == digest.id)
            )
        ).scalars()
    )
    assert impressions
    exploration = [imp for imp in impressions if imp.exploration]
    # exploration_count(min(2, ceil(0.1*N))) over >=6 ranked items => >=1 slot.
    assert exploration, "expected at least one exploration slot"
    for imp in exploration:
        assert 0.0 < imp.propensity <= 1.0
        # Exploration items never lead (A6).
        assert imp.section != "lead"


@pytest.mark.asyncio
async def test_new_users_explore_even_with_the_flag_off(db_session, monkeypatch, test_user_data):
    """CS-04: the first 14 days force exploration slots on."""
    from datetime import UTC, datetime, timedelta

    from app.config import get_settings
    from app.models.digest import DigestImpression
    from app.services.digest.builder import build_digest

    monkeypatch.setattr(get_settings(), "ranking_exploration_enabled", False)
    user, _src_a = await _seed(db_session, followed_per_source=3)
    other_src = Source(user_id=user.id, url="https://c9.example/feed", name="C")
    db_session.add(other_src)
    await db_session.flush()
    for i in range(3):
        db_session.add(
            _item(
                other_src.id,
                f"https://c9.example/{i}",
                f"followed-c{i}",
                topics=[f"c{i}"],
                reading_time=10,
            )
        )
    await db_session.commit()

    digest = await build_digest(user, db_session)
    await db_session.commit()

    impressions = list(
        (
            await db_session.execute(
                select(DigestImpression).where(DigestImpression.digest_id == digest.id)
            )
        ).scalars()
    )
    exploration = [imp for imp in impressions if imp.exploration]
    # User created moments ago (< 14 days): slots fire despite the flag.
    assert exploration, "new user should get exploration slots with the flag off"
    for imp in exploration:
        assert 0.0 < imp.propensity <= 1.0


@pytest.mark.asyncio
async def test_single_user_never_touches_collaborative_paths(db_session):
    """CS-04: with one active user the collaborative warmup is a safe no-op."""
    from app.services.cold_start.collaborative import get_collaborative_warmup_items

    user = User(email="solo-cs4@example.com", hashed_password="x", onboarding_complete=True)
    db_session.add(user)
    await db_session.commit()

    items = await get_collaborative_warmup_items(user, limit=10, session=db_session)
    assert items == []
