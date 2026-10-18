"""Pairwise weight learning from within-digest preferences (#154)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models.content import ContentItem, UserContentInteraction
from app.models.digest import Digest, DigestImpression, RankerWeightRevision
from app.models.meta_weights import UserMetaWeights
from app.models.user import User
from app.services.ranking.contract import SIGNALS
from app.services.ranking.learner import digest_pairs, prior_vector, train_user

NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)


def _features(**overrides: float) -> dict[str, float]:
    base = {name: 0.5 for name in SIGNALS}
    base.update(overrides)
    return base


async def _user(session) -> User:
    user = User(email=f"l{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    session.add(user)
    await session.flush()
    return user


async def _digest(
    session, user, *, age_hours: float, rows: list[dict], viewed: bool = True
) -> Digest:
    digest = Digest(user_id=user.id, generated_at=NOW - timedelta(hours=age_hours))
    session.add(digest)
    await session.flush()
    for pos, row in enumerate(rows):
        item = ContentItem(url=f"https://l.example/{uuid.uuid4().hex}", title="t")
        session.add(item)
        await session.flush()
        session.add(
            DigestImpression(
                user_id=user.id,
                content_item_id=item.id,
                digest_id=digest.id,
                position=pos,
                features_json=row["features"],
                viewed=viewed,
                exploration=row.get("exploration", False),
                propensity=row.get("propensity", 1.0),
            )
        )
        if row.get("interaction") is not None:
            session.add(
                UserContentInteraction(
                    user_id=user.id, content_item_id=item.id, **row["interaction"]
                )
            )
    await session.flush()
    return digest


def _long_reader_digest() -> list[dict]:
    opened = NOW - timedelta(days=2)
    return [
        {
            "features": _features(content_quality=0.9, reading_depth=0.85),
            "interaction": {"read_completion_pct": 0.95, "opened_at": opened},
        },
        {
            "features": _features(content_quality=0.2, reading_depth=0.2),
            "interaction": {"skipped": True},
        },
        {
            "features": _features(content_quality=0.3, reading_depth=0.3, temporal_context=0.9),
            "interaction": {"read_completion_pct": 0.1, "opened_at": opened},
        },
    ]


@pytest.mark.asyncio
async def test_long_form_reader_shifts_weight_toward_quality_and_depth(db_session):
    user = await _user(db_session)
    for d in range(20):
        await _digest(db_session, user, age_hours=24 * (20 - d) + 13, rows=_long_reader_digest())
    await db_session.commit()

    result = await train_user(user.id, db_session, now=NOW)
    await db_session.commit()

    prior = dict(zip(SIGNALS, prior_vector(), strict=True))
    weights = result["weights"]
    assert result["pairs"] >= 30
    assert weights["content_quality"] > prior["content_quality"]
    assert weights["reading_depth"] > prior["reading_depth"]
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    revisions = (await db_session.execute(select(func.count(RankerWeightRevision.id)))).scalar()
    assert revisions == 1

    again = await train_user(user.id, db_session, now=NOW)
    assert again["status"] == "nothing_new"  # each digest trains exactly once


@pytest.mark.asyncio
async def test_weights_stay_at_the_prior_until_enough_pairs(db_session):
    user = await _user(db_session)
    await _digest(db_session, user, age_hours=30, rows=_long_reader_digest())
    await db_session.commit()

    result = await train_user(user.id, db_session, now=NOW)

    row = (
        await db_session.execute(select(UserMetaWeights).where(UserMetaWeights.user_id == user.id))
    ).scalar_one()
    assert 0 < result["pairs"] < 30
    for i, name in enumerate(SIGNALS):
        assert row.weights[name] == pytest.approx(prior_vector()[i])
    assert row.pairs_seen == result["pairs"]


@pytest.mark.asyncio
async def test_unviewed_digest_skips_do_not_train(db_session):
    user = await _user(db_session)
    rows = [
        {"features": _features(content_quality=0.9), "interaction": {"saved": True}},
        {"features": _features(content_quality=0.1), "interaction": {"skipped": True}},
    ]
    digest = await _digest(db_session, user, age_hours=30, rows=rows, viewed=False)
    impressions = list(
        (
            await db_session.execute(
                select(DigestImpression).where(DigestImpression.digest_id == digest.id)
            )
        ).scalars()
    )
    interactions = {
        ix.content_item_id: ix
        for ix in (
            await db_session.execute(
                select(UserContentInteraction).where(UserContentInteraction.user_id == user.id)
            )
        ).scalars()
    }
    # The saved item is positive, but the skip is unseen: no pair can form.
    assert digest_pairs(impressions, interactions, now=NOW) == []


@pytest.mark.asyncio
async def test_recent_digests_wait_until_settled(db_session):
    user = await _user(db_session)
    await _digest(db_session, user, age_hours=2, rows=_long_reader_digest())
    await db_session.commit()
    assert (await train_user(user.id, db_session, now=NOW))["status"] == "nothing_new"


@pytest.mark.asyncio
async def test_other_users_digests_never_train_this_user(db_session):
    me, other = await _user(db_session), await _user(db_session)
    for d in range(15):
        await _digest(db_session, other, age_hours=24 * d + 13, rows=_long_reader_digest())
    await db_session.commit()
    assert (await train_user(me.id, db_session, now=NOW))["status"] == "nothing_new"


@pytest.mark.asyncio
async def test_exploration_pairs_are_inverse_propensity_weighted(db_session):
    user = await _user(db_session)
    opened = NOW - timedelta(days=1)
    rows = [
        {
            "features": _features(novelty=0.9),
            "interaction": {"read_completion_pct": 0.95, "opened_at": opened},
            "exploration": True,
            "propensity": 0.25,
        },
        {"features": _features(novelty=0.1), "interaction": {"skipped": True}},
    ]
    digest = await _digest(db_session, user, age_hours=30, rows=rows)
    impressions = list(
        (
            await db_session.execute(
                select(DigestImpression).where(DigestImpression.digest_id == digest.id)
            )
        ).scalars()
    )
    interactions = {
        ix.content_item_id: ix
        for ix in (
            await db_session.execute(
                select(UserContentInteraction).where(UserContentInteraction.user_id == user.id)
            )
        ).scalars()
    }
    [(_, _, weight)] = digest_pairs(impressions, interactions, now=NOW)
    assert weight == pytest.approx(0.5 * 4.0)  # min confidence (skip 0.5) x IPW (1/0.25)


@pytest.mark.asyncio
async def test_opening_a_digest_marks_its_impressions_viewed(client, db_session):
    data = {"email": f"v{uuid.uuid4().hex[:6]}@example.com", "password": "TestPass123!"}
    reg = await client.post("/api/v1/auth/register", json=data)
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    user = (await db_session.execute(select(User).where(User.email == data["email"]))).scalar_one()
    digest = await _digest(db_session, user, age_hours=1, rows=_long_reader_digest(), viewed=False)
    digest_id = digest.id
    await db_session.commit()

    resp = await client.get(f"/api/v1/digest/{digest_id}", headers=headers)

    assert resp.status_code == 200
    db_session.expire_all()
    flags = (
        (
            await db_session.execute(
                select(DigestImpression.viewed).where(DigestImpression.digest_id == digest_id)
            )
        )
        .scalars()
        .all()
    )
    assert flags and all(flags)
