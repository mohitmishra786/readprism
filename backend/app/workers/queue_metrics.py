"""Queue latency and digest on-time telemetry (#239).

Celery signal handlers, connected by importing this module from celery_app:

- every published task gets an `rp_enqueued_at` header; when a worker
  starts it, the wait is recorded per queue (`lag`), and when it ends, the
  runtime is recorded per task name (`run`);
- the daily scheduler stamps `rp_due_at` on each digest build. The header
  is copied onto tasks enqueued while that task runs, so the delivery task
  inherits it; when delivery finishes, the time since `rp_due_at` is the
  digest's end-to-end lateness (`e2e`), counted against
  DIGEST_ON_TIME_SECONDS.

Samples go to Redis lists per hour (last 2,000 per list, kept 3 days) and
are summarised by app.services.metrics.queues. Failures here are logged
and never affect the task.
"""

from __future__ import annotations

import contextvars
import time

from celery import signals  # type: ignore[import-untyped]

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

DELIVER_TASK = "app.workers.tasks.deliver_digest.deliver_digest_task"
MAX_SAMPLES = 2000
TTL_SECONDS = 3 * 86400

_due: contextvars.ContextVar[float | None] = contextvars.ContextVar("rp_due_at", default=None)
_started: dict[str, float] = {}
_client = None


def _redis():
    global _client
    if _client is None:
        import redis

        _client = redis.Redis.from_url(get_settings().redis_url, socket_timeout=1)
    return _client


def hour_key(ts: float) -> str:
    return time.strftime("%Y%m%d%H", time.gmtime(ts))


def record(kind: str, name: str, seconds: float, *, now: float | None = None) -> None:
    key = f"qm:{kind}:{name}:{hour_key(now or time.time())}"
    try:
        pipe = _redis().pipeline()
        pipe.lpush(key, round(max(0.0, seconds), 3))
        pipe.ltrim(key, 0, MAX_SAMPLES - 1)
        pipe.expire(key, TTL_SECONDS)
        pipe.execute()
    except Exception as e:  # metrics must never break a task
        logger.debug(f"queue metrics: could not record {key}: {e}")


def _header(request, name: str) -> float | None:
    value = getattr(request, name, None)
    if value is None:
        value = (getattr(request, "headers", None) or {}).get(name)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@signals.before_task_publish.connect
def stamp_headers(headers=None, **_kwargs) -> None:
    if headers is None:
        return
    headers.setdefault("rp_enqueued_at", time.time())
    due = _due.get()
    if due is not None:
        headers.setdefault("rp_due_at", due)


@signals.task_prerun.connect
def task_started(task_id=None, task=None, **_kwargs) -> None:
    if task is None or task_id is None:
        return
    now = time.time()
    request = task.request
    enqueued = _header(request, "rp_enqueued_at")
    if enqueued is not None:
        queue = (getattr(request, "delivery_info", None) or {}).get("routing_key") or "celery"
        record("lag", queue, now - enqueued, now=now)
    _started[task_id] = now
    _due.set(_header(request, "rp_due_at"))


@signals.task_postrun.connect
def task_finished(task_id=None, task=None, state=None, **_kwargs) -> None:
    if task is None or task_id is None:
        return
    now = time.time()
    started = _started.pop(task_id, None)
    if started is not None:
        record("run", task.name, now - started, now=now)
    due = _due.get()
    if task.name == DELIVER_TASK and due is not None and state == "SUCCESS":
        record("e2e", "digest", now - due, now=now)
    _due.set(None)
