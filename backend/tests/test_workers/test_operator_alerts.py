"""Operator alerts (#171)."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.config import get_settings
from app.models.content import ContentItem
from app.models.source import Source
from app.models.user import User
from app.services import alerts

NOW = time.time()


def _report(waits=None, ratio=None, e2e=0):
    return {
        "queue_wait_seconds": waits or {},
        "task_runtime_seconds": {},
        "digest_delivery": {"on_time_ratio": ratio, "lateness_seconds": {"count": e2e}},
    }


class FakeRedis:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.hashes: dict[str, dict[str, str]] = {}

    async def get(self, key):
        return self.values.get(key)

    async def llen(self, key):
        return 0

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    async def hdel(self, key, field):
        self.hashes.get(key, {}).pop(field, None)


@pytest.fixture(autouse=True)
def _quiet_health():
    with patch("app.services.instance_health.check", AsyncMock(return_value=[])):
        yield


async def _stale_feed(db_session, hours):
    user = User(email=f"a{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        Source(user_id=user.id, url="https://a.example/feed", name="A", source_type="rss")
    )
    db_session.add(
        ContentItem(
            url=f"https://a.example/{uuid.uuid4().hex}",
            title="t",
            fetched_at=datetime.now(UTC) - timedelta(hours=hours),
        )
    )
    await db_session.commit()


async def _keys(db_session, *, redis=None, report=None, now=NOW):
    found = await alerts.evaluate(
        db_session,
        now=now,
        redis=redis or FakeRedis(),
        queue_report=lambda *a, **k: report or _report(),
    )
    return [a.key for a in found]


@pytest.mark.asyncio
async def test_simulated_ingest_stall_alerts_after_two_hours(db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "alert_disk_paths", "")
    await _stale_feed(db_session, hours=1.5)
    assert await _keys(db_session, now=time.time()) == []
    await db_session.execute(
        ContentItem.__table__.update().values(fetched_at=datetime.now(UTC) - timedelta(hours=2.1))
    )
    await db_session.commit()
    # The current time, not import time: the suite can run long enough that
    # "2.1 hours ago" measured from import looks like under 2 hours.
    assert await _keys(db_session, now=time.time()) == ["ingest_stall"]


@pytest.mark.asyncio
async def test_queue_lag_uses_adr_targets(db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "alert_disk_paths", "")
    report = _report(
        waits={
            "digest": {"count": 50, "p95": 75.0},
            "embed": {"count": 50, "p95": 500.0},  # under the 10 min target
            "scrape": {"count": 50, "p95": 9999.0},  # no target for scrape
        },
        ratio=0.95,
        e2e=40,
    )
    assert await _keys(db_session, report=report) == ["queue_lag:digest", "digest_late"]


@pytest.mark.asyncio
async def test_error_rates_disk_and_backup(db_session, monkeypatch):
    from app.services.metrics.prometheus import LLM_CALLS_KEY
    from app.workers.queue_metrics import hour_key

    hour = hour_key(NOW)
    redis = FakeRedis(
        {
            f"http:all:{hour}": "100",
            f"http:5xx:{hour}": "9",
            LLM_CALLS_KEY.format(outcome="ok", hour=hour): "2",
            LLM_CALLS_KEY.format(outcome="error", hour=hour): "8",
            alerts.BACKUP_KEY: str(NOW - 40 * 3600),
        }
    )
    monkeypatch.setattr(get_settings(), "alert_disk_percent", 0)
    keys = await _keys(db_session, redis=redis)
    assert keys == ["http_5xx", "llm_errors", "disk:/", "backup"]


@pytest.mark.asyncio
async def test_notifies_once_repeats_and_resolves(db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "alert_ntfy_url", "https://ntfy.example/rp")
    monkeypatch.setattr(get_settings(), "alert_repeat_hours", 12)
    redis = FakeRedis()
    firing = [alerts.Alert("ingest_stall", "No new items for 3.0 hours.")]
    notify = AsyncMock(return_value=1)
    with (
        patch.object(alerts, "_notify", notify),
        patch.object(alerts, "evaluate", AsyncMock(return_value=firing)),
    ):
        first = await alerts.run(db_session, now=NOW, redis=redis)
        again = await alerts.run(db_session, now=NOW + 600, redis=redis)
        later = await alerts.run(db_session, now=NOW + 13 * 3600, redis=redis)
    assert (
        first["sent"] == ["ingest_stall"]
        and again["sent"] == []
        and later["sent"] == ["ingest_stall"]
    )
    with (
        patch.object(alerts, "_notify", notify),
        patch.object(alerts, "evaluate", AsyncMock(return_value=[])),
    ):
        done = await alerts.run(db_session, now=NOW + 14 * 3600, redis=redis)
    assert done["resolved"] == ["ingest_stall"]
    assert notify.await_args.args[0] == "[Weirling] Resolved: ingest_stall"
    assert notify.await_count == 3


@pytest.mark.asyncio
async def test_ntfy_delivery(monkeypatch):
    import httpx

    monkeypatch.setattr(get_settings(), "alert_ntfy_url", "https://ntfy.example/rp")
    monkeypatch.setattr(get_settings(), "alert_email", "")
    seen = {}

    async def fake_post(self, url, content=None, headers=None):
        seen.update(url=url, body=content, title=headers["Title"])
        return httpx.Response(200)

    with patch("httpx.AsyncClient.post", fake_post):
        assert await alerts._notify("[Weirling] x", "body") == 1
    assert seen == {"url": "https://ntfy.example/rp", "body": b"body", "title": "[Weirling] x"}


def test_alerts_are_scheduled_on_two_queues():
    from app.workers.celery_app import celery_app

    queues = {
        e["options"]["queue"]
        for e in celery_app.conf.beat_schedule.values()
        if e["task"] == "app.workers.tasks.alerts.check_alerts"
    }
    assert queues == {"scrape", "digest"}


@pytest.mark.asyncio
async def test_api_requests_are_counted_for_the_error_rate(client):
    from app.utils.cache import get_redis
    from app.workers.queue_metrics import hour_key

    key = f"http:all:{hour_key(time.time())}"
    before = int(await get_redis().get(key) or 0)
    await client.get("/health")
    assert int(await get_redis().get(key) or 0) == before + 1
