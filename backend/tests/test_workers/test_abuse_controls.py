"""Hosted abuse controls: fetch budgets, per-host caps, inbound caps (#169)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.feed import Feed
from app.models.source import Source
from app.models.user import User
from app.services import abuse
from app.services.ingestion.rss_parser import RawContentItem
from tests.conftest import TestingSessionLocal


@pytest.fixture
def counters():
    store: dict[str, int] = {}

    async def incr(key, amount=1, ttl_seconds=3600):
        store[key] = store.get(key, 0) + amount
        return store[key]

    with patch("app.utils.cache.cache_incr", incr):
        yield store


@pytest.fixture
def hosted(monkeypatch):
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "deployment_mode", "hosted")
    monkeypatch.setattr(s, "registration_mode", "open")
    monkeypatch.setattr(s, "email_verification", "off")
    return s


async def _account(db_session, feeds: list[str]) -> User:
    user = User(
        email=f"ab{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="x",
        onboarding_complete=True,
    )
    db_session.add(user)
    await db_session.flush()
    for url in feeds:
        db_session.add(Source(user_id=user.id, url=url, feed_url=url))
    await db_session.commit()
    return user


async def _poll(calls: list[str]):
    from app.workers.tasks import ingest_feeds

    async def dispatch(target, session):
        calls.append(target.feed_url or target.url)
        return [RawContentItem(url=f"{target.feed_url}/1", title="x", guid="1")]

    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.services.ingestion.dispatcher.dispatch_source", dispatch),
        patch("app.workers.tasks.compute_embeddings.compute_embedding_for_item.delay"),
    ):
        return await ingest_feeds._ingest_all_feeds_async()


@pytest.mark.asyncio
async def test_over_budget_account_is_paused_with_a_notice(
    db_session, hosted, counters, monkeypatch
):
    monkeypatch.setattr(hosted, "hosted_fetch_budget_per_hour", 3)
    abuser = await _account(db_session, [f"https://victim{i}.example/rss" for i in range(6)])
    calls: list[str] = []

    await _poll(calls)

    assert len(calls) == 3  # the rest wait for the next hour
    async with TestingSessionLocal() as s:
        user = await s.get(User, abuser.id)
        waiting = list(
            (await s.execute(select(Feed).where(Feed.next_poll_at > datetime.now(UTC)))).scalars()
        )
    assert user.fetch_paused_until is not None and user.fetch_paused_until > datetime.now(UTC)
    assert len(waiting) == 6  # 3 polled (normal schedule) + 3 deferred to next hour


@pytest.mark.asyncio
async def test_a_shared_feed_keeps_flowing_while_any_subscriber_has_budget(
    db_session, hosted, counters, monkeypatch
):
    monkeypatch.setattr(hosted, "hosted_fetch_budget_per_hour", 1)
    shared = "https://popular.example/rss"
    heavy = await _account(db_session, ["https://heavy.example/rss", shared])
    await _account(db_session, [shared])
    # The heavy account already spent its budget this hour.
    await abuse.charge_fetch(heavy.id)
    calls: list[str] = []

    await _poll(calls)

    assert shared in calls
    assert "https://heavy.example/rss" not in calls


@pytest.mark.asyncio
async def test_host_poll_cap_applies_across_accounts(db_session, hosted, counters, monkeypatch):
    monkeypatch.setattr(hosted, "hosted_host_polls_per_hour", 2)
    for i in range(3):
        await _account(db_session, [f"https://one-host.example/feed-{i}"])
    calls: list[str] = []

    await _poll(calls)

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_selfhost_has_no_budget(db_session, counters, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "hosted_fetch_budget_per_hour", 1)
    await _account(db_session, [f"https://own{i}.example/rss" for i in range(4)])
    calls: list[str] = []
    await _poll(calls)
    assert len(calls) == 4 and counters == {}


@pytest.mark.asyncio
async def test_sources_per_host_cap_and_on_demand_budget(client, hosted, counters, monkeypatch):
    monkeypatch.setattr(hosted, "hosted_max_sources_per_host", 2)
    monkeypatch.setattr(hosted, "hosted_fetch_budget_per_hour", 3)
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": f"sh{uuid.uuid4().hex[:6]}@example.com", "password": "TestPass123!"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    with (
        patch("app.api.sources._autodiscover_feed", AsyncMock(return_value=None)),
        patch("app.workers.tasks.ingest_feeds.ingest_user_sources.delay") as per_user,
        patch("app.workers.tasks.ingest_feeds.ingest_all_feeds.delay") as everyone,
    ):
        codes = [
            (
                await client.post(
                    "/api/v1/sources", json={"url": f"https://same.example/{i}"}, headers=headers
                )
            ).status_code
            for i in range(3)
        ]
        assert codes == [201, 201, 422]
        assert everyone.call_count == 0 and per_user.call_count == 2

        ok = await client.post(
            "/api/v1/sources", json={"url": "https://b.example"}, headers=headers
        )
        over = await client.post(
            "/api/v1/sources", json={"url": "https://c.example"}, headers=headers
        )
    assert ok.status_code == 201
    assert over.status_code == 429 and "Retry-After" in over.headers
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert me["fetch_paused_until"] is not None


@pytest.mark.asyncio
async def test_inbound_caps(hosted, counters, monkeypatch):
    monkeypatch.setattr(hosted, "hosted_inbound_per_day", 2)
    monkeypatch.setattr(hosted, "hosted_inbound_mb_per_day", 1)
    monkeypatch.setattr(hosted, "inbound_max_message_bytes", 600_000)
    uid = uuid.uuid4()

    assert await abuse.inbound_allowed(uid, 700_000) == (False, "message too large")
    assert (await abuse.inbound_allowed(uid, 500_000))[0]
    assert (await abuse.inbound_allowed(uid, 500_000))[0]
    assert await abuse.inbound_allowed(uid, 10) == (False, "daily newsletter count reached")

    other = uuid.uuid4()
    monkeypatch.setattr(hosted, "hosted_inbound_per_day", 0)
    assert (await abuse.inbound_allowed(other, 590_000))[0]
    assert await abuse.inbound_allowed(other, 590_000) == (False, "daily newsletter volume reached")


@pytest.mark.asyncio
async def test_selfhost_still_drops_oversized_messages(counters):
    assert (await abuse.inbound_allowed(uuid.uuid4(), 10))[0]
    assert not (await abuse.inbound_allowed(uuid.uuid4(), 50_000_000))[0]
    assert counters == {}
