"""Collaborative warmup from k-anonymous crowd signals (#210)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.content import ContentItem, UserContentInteraction
from app.models.interest_graph import InterestNode
from app.models.user import User
from app.services.cold_start import collaborative
from app.services.cold_start.collaborative import get_collaborative_warmup_items


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(collaborative.settings, "cold_start_collaborative_enabled", True)
    monkeypatch.setattr(collaborative.settings, "collaborative_warmup_min_users", 1)
    monkeypatch.setattr(collaborative.settings, "collaborative_k_anonymity", 20)


async def _readers(db_session, n: int, *, opted_out: int = 0) -> list[User]:
    users = [
        User(
            email=f"crowd{i}-{uuid.uuid4().hex[:6]}@example.com",
            hashed_password="x",
            collaborative_opt_out=i < opted_out,
        )
        for i in range(n)
    ]
    db_session.add_all(users)
    await db_session.flush()
    return users


async def _item(db_session, topic: str, **kw) -> ContentItem:
    item = ContentItem(
        url=f"https://crowd.example/{uuid.uuid4().hex}", title=topic, topic_clusters=[topic], **kw
    )
    db_session.add(item)
    await db_session.flush()
    return item


def _engage(db_session, users, item, *, days_ago: float = 1):
    for u in users:
        ix = UserContentInteraction(user_id=u.id, content_item_id=item.id, read_completion_pct=0.95)
        db_session.add(ix)
        ix.updated_at = datetime.now(UTC) - timedelta(days=days_ago)


async def _newcomer(db_session, topic: str | None = "databases") -> User:
    user = User(email=f"new-{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    if topic:
        db_session.add(InterestNode(user_id=user.id, topic_label=topic, weight=0.6))
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_new_user_with_topics_gets_crowd_items_only_at_k(db_session):
    crowd = await _readers(db_session, 20)
    popular = await _item(db_session, "databases")
    almost = await _item(db_session, "databases")
    off_topic = await _item(db_session, "knitting")
    _engage(db_session, crowd, popular)
    _engage(db_session, crowd[:19], almost)  # one short of k
    _engage(db_session, crowd, off_topic)
    newcomer = await _newcomer(db_session)

    items = await get_collaborative_warmup_items(newcomer, limit=10, session=db_session)

    assert [i.id for i in items] == [popular.id]


@pytest.mark.asyncio
async def test_opted_out_readers_do_not_count_towards_k(db_session):
    crowd = await _readers(db_session, 20, opted_out=1)
    item = await _item(db_session, "databases")
    _engage(db_session, crowd, item)
    newcomer = await _newcomer(db_session)

    assert await get_collaborative_warmup_items(newcomer, limit=10, session=db_session) == []


@pytest.mark.asyncio
async def test_private_and_stale_items_never_qualify(db_session):
    crowd = await _readers(db_session, 20)
    private = await _item(db_session, "databases", owner_user_id=crowd[0].id)
    stale = await _item(db_session, "databases")
    _engage(db_session, crowd, private)
    _engage(db_session, crowd, stale, days_ago=30)
    newcomer = await _newcomer(db_session)

    assert await get_collaborative_warmup_items(newcomer, limit=10, session=db_session) == []


@pytest.mark.asyncio
async def test_newcomer_without_interests_gets_nothing(db_session):
    crowd = await _readers(db_session, 20)
    item = await _item(db_session, "databases")
    _engage(db_session, crowd, item)
    newcomer = await _newcomer(db_session, topic=None)

    assert await get_collaborative_warmup_items(newcomer, limit=10, session=db_session) == []


@pytest.mark.asyncio
async def test_gated_off_below_min_active_users(db_session, monkeypatch):
    monkeypatch.setattr(collaborative.settings, "collaborative_warmup_min_users", 1000)
    crowd = await _readers(db_session, 20)
    item = await _item(db_session, "databases")
    _engage(db_session, crowd, item)
    newcomer = await _newcomer(db_session)

    assert await get_collaborative_warmup_items(newcomer, limit=10, session=db_session) == []


@pytest.mark.asyncio
async def test_disabled_flag(db_session, monkeypatch):
    monkeypatch.setattr(collaborative.settings, "cold_start_collaborative_enabled", False)
    newcomer = await _newcomer(db_session)
    assert await get_collaborative_warmup_items(newcomer, limit=10, session=db_session) == []


@pytest.mark.asyncio
async def test_opt_out_is_a_preference(client):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": f"oo{uuid.uuid4().hex[:6]}@example.com", "password": "TestPass123!"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert me["collaborative_opt_out"] is False
    resp = await client.put(
        "/api/v1/preferences", json={"collaborative_opt_out": True}, headers=headers
    )
    assert resp.status_code == 200 and resp.json()["collaborative_opt_out"] is True
