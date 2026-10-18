"""Queue latency and digest on-time telemetry (#239)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.workers import queue_metrics as qm


class FakeRedis:
    def __init__(self):
        self.lists: dict[str, list] = {}

    def pipeline(self):
        return self

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, str(value))

    def ltrim(self, key, start, end):
        self.lists[key] = self.lists[key][start : end + 1]

    def expire(self, key, ttl):
        pass

    def execute(self):
        return []

    def scan_iter(self, match="*", count=None):
        return list(self.lists)

    def lrange(self, key, start, end):
        return self.lists.get(key, [])


@pytest.fixture
def redis():
    fake = FakeRedis()
    with patch.object(qm, "_redis", return_value=fake):
        yield fake


def _task(name, *, queue="digest", **headers):
    request = SimpleNamespace(delivery_info={"routing_key": queue}, headers=None, **headers)
    return SimpleNamespace(name=name, request=request)


def test_wait_and_runtime_are_recorded_per_queue_and_task(redis):
    task = _task("app.workers.tasks.x", queue="embed", rp_enqueued_at=time.time() - 4)
    qm.task_started(task_id="t1", task=task)
    qm.task_finished(task_id="t1", task=task, state="SUCCESS")

    from app.services.metrics.queues import queue_report

    report = queue_report(redis)
    assert report["queue_wait_seconds"]["embed"]["count"] == 1
    assert 3.5 < report["queue_wait_seconds"]["embed"]["p50"] < 5
    assert report["task_runtime_seconds"]["app.workers.tasks.x"]["count"] == 1
    assert report["digest_delivery"]["on_time_ratio"] is None


def test_due_time_follows_the_build_into_delivery(redis, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "digest_on_time_seconds", 600)
    due = time.time() - 120

    # The scheduled build runs with rp_due_at; delivery enqueued inside inherits it.
    build = _task("app.workers.tasks.build_digest.build_digest_for_user", rp_due_at=due)
    qm.task_started(task_id="b", task=build)
    published: dict = {}
    qm.stamp_headers(headers=published)
    qm.task_finished(task_id="b", task=build, state="SUCCESS")
    assert published["rp_due_at"] == due and "rp_enqueued_at" in published

    # Outside a due task nothing is inherited.
    plain: dict = {}
    qm.stamp_headers(headers=plain)
    assert "rp_due_at" not in plain

    deliver = _task(qm.DELIVER_TASK, **published)
    qm.task_started(task_id="d", task=deliver)
    qm.task_finished(task_id="d", task=deliver, state="SUCCESS")
    late = _task(qm.DELIVER_TASK, rp_due_at=time.time() - 3600)
    qm.task_started(task_id="d2", task=late)
    qm.task_finished(task_id="d2", task=late, state="SUCCESS")

    from app.services.metrics.queues import queue_report

    delivery = queue_report(redis)["digest_delivery"]
    assert delivery["lateness_seconds"]["count"] == 2
    assert delivery["on_time_ratio"] == 0.5


def test_metrics_failures_never_break_tasks():
    with patch.object(qm, "_redis", side_effect=RuntimeError("redis down")):
        task = _task("t", rp_enqueued_at=time.time())
        qm.task_started(task_id="x", task=task)
        qm.task_finished(task_id="x", task=task, state="SUCCESS")


@pytest.mark.asyncio
async def test_queue_endpoint_requires_the_metrics_token(client, monkeypatch, redis):
    from app.api import metrics

    monkeypatch.setattr(metrics.settings, "metrics_token", "m-token")
    assert (await client.get("/api/v1/metrics/queues")).status_code in (401, 403)
    ok = await client.get("/api/v1/metrics/queues", headers={"X-Metrics-Token": "m-token"})
    assert ok.status_code == 200 and "digest_delivery" in ok.json()


def test_scheduler_stamps_the_due_time():
    from app.workers.tasks import build_digest as bd

    user = SimpleNamespace(id="u1", onboarding_complete=True)
    with (
        patch.object(bd, "_is_digest_time_for_user", return_value=True),
        patch.object(bd.build_digest_for_user, "apply_async") as send,
    ):
        import asyncio

        class Rows:
            def scalars(self):
                return SimpleNamespace(all=lambda: [user])

        class Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def execute(self, _q):
                return Rows()

        with patch("app.database.AsyncSessionLocal", Session):
            asyncio.run(bd._schedule_digests_async())
    args, kwargs = send.call_args
    assert args == (("u1",),) and "rp_due_at" in kwargs["headers"]
