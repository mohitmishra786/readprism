"""Day-7 'your digest vs newest-first' (#237)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.digest import Digest, DigestImpression, DigestItem
from app.models.user import User

NOW = datetime.now(UTC)


async def _login(client, db_session, *, age_days=10):
    email = f"vs{uuid.uuid4().hex[:6]}@example.com"
    reg = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "TestPass123!"}
    )
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.created_at = NOW - timedelta(days=age_days)
    await db_session.commit()
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}, user


async def _digest(db_session, user, *, finished_index=0, team=False):
    """10 items: item i is newer the larger i is, so newest-first is the reverse.
    PRS put `finished_index` at that position; the reader finished it."""
    digest = Digest(user_id=user.id, total_items=10, generated_at=NOW - timedelta(days=2))
    db_session.add(digest)
    await db_session.flush()
    items = []
    for i in range(10):
        item = ContentItem(
            url=f"https://vs.example/{uuid.uuid4().hex}",
            title=f"Item {i}",
            fetched_at=NOW - timedelta(days=3, hours=-i),
        )
        db_session.add(item)
        await db_session.flush()
        db_session.add(
            DigestItem(
                digest_id=digest.id,
                content_item_id=item.id,
                position=i,
                section="lead",
                prs_score=1 - i / 10,
                signal_breakdown={},
            )
        )
        if team:
            db_session.add(
                DigestImpression(
                    user_id=user.id,
                    content_item_id=item.id,
                    digest_id=digest.id,
                    section="lead",
                    position=i,
                    score=0.5,
                    features_json={},
                    team="prs" if i % 2 == 0 else "baseline",
                )
            )
        items.append(item)
    db_session.add(
        UserContentInteraction(
            user_id=user.id, content_item_id=items[finished_index].id, read_completion_pct=0.95
        )
    )
    await db_session.commit()
    return items


@pytest.mark.asyncio
async def test_shows_real_examples_from_the_last_week(client, db_session):
    headers, user = await _login(client, db_session)
    await _digest(db_session, user, finished_index=0)
    body = (await client.get("/api/v1/digest/vs-newest", headers=headers)).json()
    assert body["available"] is True
    example = body["examples"][0]
    assert example["title"] == "Item 0"  # oldest item: newest-first puts it last
    assert example["your_position"] == 1 and example["newest_first_position"] == 10


@pytest.mark.asyncio
async def test_hidden_when_too_new_or_not_enough_reading(client, db_session):
    headers, user = await _login(client, db_session, age_days=3)
    await _digest(db_session, user)
    assert (await client.get("/api/v1/digest/vs-newest", headers=headers)).json() == {
        "available": False,
        "reason": "too_new",
        "examples": [],
        "interleaving": None,
    }
    headers, user = await _login(client, db_session)
    await _digest(db_session, user, finished_index=9)  # newest item: newest-first agrees
    body = (await client.get("/api/v1/digest/vs-newest", headers=headers)).json()
    assert body["available"] is False and body["reason"] == "not_enough_reading"


@pytest.mark.asyncio
async def test_never_includes_other_users_data(client, db_session):
    _, other = await _login(client, db_session)
    await _digest(db_session, other, finished_index=0)
    headers, _ = await _login(client, db_session)
    body = (await client.get("/api/v1/digest/vs-newest", headers=headers)).json()
    assert body["available"] is False and body["examples"] == []


@pytest.mark.asyncio
async def test_includes_the_readers_own_interleaving_outcomes(client, db_session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "metrics_token", "ops-token")
    headers, user = await _login(client, db_session)
    await _digest(db_session, user, finished_index=0, team=True)  # item 0 is on the PRS team
    body = (await client.get("/api/v1/digest/vs-newest", headers=headers)).json()
    assert body["interleaving"] == {"digests": 1, "prs_wins": 1, "newest_wins": 0, "ties": 0}
    report = await client.get(
        "/api/v1/metrics/interleaving", headers={"X-Metrics-Token": "ops-token"}
    )
    assert report.status_code == 200 and report.json()["digests"] >= 1
    assert str(user.id) not in report.text  # no user ids reintroduced into the operator metric
