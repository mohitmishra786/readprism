"""Instance health banner for the owner (#234)."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import select

from app.models.content import ContentItem
from app.models.source import Source
from app.models.user import User
from app.services import instance_health as health
from app.workers.tasks.heartbeat import HEARTBEAT_KEY, worker_key

NOW = time.time()
LONG_AGO = NOW - 86400  # API started a day ago: past the warm-up grace


class FakeRedis:
    def __init__(self, depths=None):
        self.depths = depths or {}

    async def llen(self, queue):
        return self.depths.get(queue, 0)


def _cache(values: dict):
    return patch("app.utils.cache.cache_get", AsyncMock(side_effect=lambda k: values.get(k)))


def _healthy() -> dict:
    return {HEARTBEAT_KEY: NOW, **{worker_key(q): NOW - 60 for q in ("scrape", "embed", "digest")}}


async def _keys(db_session, values, *, depths=None, started=LONG_AGO):
    with _cache(values):
        problems = await health.check(db_session, now=NOW, started=started, redis=FakeRedis(depths))
    return [p["key"] for p in problems]


@pytest.mark.asyncio
async def test_all_healthy_reports_nothing(db_session):
    assert await _keys(db_session, _healthy()) == []


@pytest.mark.asyncio
async def test_stopped_scrape_worker_is_reported_after_the_stale_window(db_session):
    values = _healthy()
    values[worker_key("scrape")] = NOW - 31 * 60  # default threshold: 30 minutes
    assert await _keys(db_session, values) == ["worker:scrape"]
    values[worker_key("scrape")] = NOW - 29 * 60
    assert await _keys(db_session, values) == []


@pytest.mark.asyncio
async def test_worker_never_seen_is_reported_only_after_warm_up(db_session):
    values = _healthy()
    del values[worker_key("embed")]
    assert await _keys(db_session, values, started=NOW - 60) == []
    assert await _keys(db_session, values) == ["worker:embed"]


@pytest.mark.asyncio
async def test_beat_down_is_one_problem_not_a_digest_worker_one_too(db_session):
    values = _healthy()
    del values[HEARTBEAT_KEY]
    values[worker_key("digest")] = NOW - 3600
    assert await _keys(db_session, values) == ["beat"]


@pytest.mark.asyncio
async def test_backlog_and_stalled_ingest(db_session):
    user = User(email=f"h{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        Source(user_id=user.id, url="https://h.example/feed", name="H", source_type="rss")
    )
    db_session.add(
        ContentItem(
            url=f"https://h.example/{uuid.uuid4().hex}",
            title="Old",
            fetched_at=datetime.now(UTC) - timedelta(hours=7),
        )
    )
    await db_session.commit()
    keys = await _keys(db_session, _healthy(), depths={"embed": 5000})
    assert keys == ["backlog:embed", "ingest"]


@pytest.mark.asyncio
async def test_llm_failure_newer_than_last_success(db_session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_api_key", "k")
    values = _healthy()
    values[health.LLM_ERROR_KEY] = {"at": NOW - 10, "reason": "HTTP 401: the API key was rejected"}
    values[health.LLM_OK_KEY] = NOW - 100
    assert await _keys(db_session, values) == ["llm"]
    values[health.LLM_OK_KEY] = NOW - 1
    assert await _keys(db_session, values) == []


@pytest.mark.asyncio
async def test_llm_client_records_a_rejected_key_without_the_key():
    from app.services.llm.client import LLMClient

    def handler(request):
        return httpx.Response(401, text="invalid api key")

    with patch("app.services.instance_health.record_llm_outcome", AsyncMock()) as record:
        llm = LLMClient(api_key="sk-secret", transport=httpx.MockTransport(handler))
        assert await llm.complete(model="m", messages=[{"role": "user", "content": "hi"}]) is None
    ok, reason = record.await_args.args
    assert ok is False and "rejected" in reason and "sk-secret" not in reason


@pytest.mark.asyncio
async def test_endpoint_shows_problems_only_to_the_owner(client, db_session):
    tokens = []
    for _ in range(2):
        email = f"o{uuid.uuid4().hex[:6]}@example.com"
        reg = await client.post(
            "/api/v1/auth/register", json={"email": email, "password": "TestPass123!"}
        )
        tokens.append({"Authorization": f"Bearer {reg.json()['access_token']}"})
        user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
        user.created_at = datetime.now(UTC) - timedelta(days=10 - len(tokens))
        await db_session.commit()
    fake = [{"key": "beat", "message": "m", "hint": "h"}]
    with patch.object(health, "check", AsyncMock(return_value=fake)):
        owner = await client.get("/api/v1/metrics/instance-health", headers=tokens[0])
        other = await client.get("/api/v1/metrics/instance-health", headers=tokens[1])
    assert owner.json() == {"owner": True, "problems": fake}
    assert other.json() == {"owner": False, "problems": []}


@pytest.mark.asyncio
async def test_queue_heartbeat_is_scheduled_on_each_queue():
    from app.workers.celery_app import celery_app

    entries = {
        e["options"]["queue"]
        for e in celery_app.conf.beat_schedule.values()
        if e["task"].endswith("queue_heartbeat")
    }
    assert entries == {"scrape", "embed", "digest"}
