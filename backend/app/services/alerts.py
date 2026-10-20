"""Operator alerts for the known failure modes (#171).

A beat task evaluates these every 10 minutes and notifies the operator by
ntfy (ALERT_NTFY_URL) and/or email (ALERT_EMAIL):

- ingest stall: no new items for ALERT_INGEST_STALL_HOURS (default 2);
- queue lag, against docs/adr/0001-celery-solo-pool.md: digest queue wait
  p95 over 60 s, embed queue wait p95 over 10 min, digest on-time below 99%;
- API 5xx rate over ALERT_5XX_RATE in the last hour;
- disk use over ALERT_DISK_PERCENT on ALERT_DISK_PATHS;
- backups: the last successful scripts/backup.sh is older than
  ALERT_BACKUP_MAX_AGE_HOURS (only once a backup has ever succeeded);
- LLM error rate over ALERT_LLM_ERROR_RATE in the last hour;
- a stopped worker queue or scheduler (from the #234 health checks).

Each alert is sent when it starts, repeated every ALERT_REPEAT_HOURS while it
lasts, and followed by a "resolved" note. Nothing here includes secrets.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ADR 0001 targets.
DIGEST_WAIT_P95_SECONDS = 60
EMBED_WAIT_P95_SECONDS = 600
DIGEST_ON_TIME_TARGET = 0.99
MIN_SAMPLES = 20

HTTP_COUNT_KEY = "http:{kind}:{hour}"  # kind: all | 5xx
BACKUP_KEY = "backup:last_success"
ACTIVE_KEY = "alerts:active"  # hash: alert key -> "first_seen,last_sent"


@dataclass(frozen=True)
class Alert:
    key: str
    message: str


async def record_http(status_code: int) -> None:
    """Hourly request and 5xx counts in Redis, for the error-rate alert."""
    from app.utils.cache import cache_incr
    from app.workers.queue_metrics import hour_key

    hour = hour_key(time.time())
    await cache_incr(HTTP_COUNT_KEY.format(kind="all", hour=hour), ttl_seconds=2 * 86400)
    if status_code >= 500:
        await cache_incr(HTTP_COUNT_KEY.format(kind="5xx", hour=hour), ttl_seconds=2 * 86400)


async def _count(redis, key: str) -> int:
    value = await redis.get(key)
    return int(value) if value is not None else 0


async def evaluate(
    session: AsyncSession, *, now: float | None = None, redis=None, queue_report=None
) -> list[Alert]:
    from app.models.content import ContentItem
    from app.models.source import Source
    from app.services import instance_health
    from app.services.metrics.prometheus import LLM_CALLS_KEY
    from app.services.metrics.queues import queue_report as default_report
    from app.utils.cache import get_redis
    from app.workers.queue_metrics import _redis as sync_redis
    from app.workers.queue_metrics import hour_key

    s = get_settings()
    now = now or time.time()
    redis = redis or get_redis()
    alerts: list[Alert] = []

    # Ingest stall.
    has_sources = (
        await session.execute(select(func.count(Source.id)).where(Source.is_active.is_(True)))
    ).scalar()
    latest = (await session.execute(select(func.max(ContentItem.fetched_at)))).scalar()
    if has_sources and latest is not None:
        age_h = (now - latest.timestamp()) / 3600
        if age_h >= s.alert_ingest_stall_hours:
            alerts.append(Alert("ingest_stall", f"No new items for {age_h:.1f} hours."))

    # Queue lag and digest punctuality (last hour; ADR 0001 targets).
    report = (queue_report or default_report)(sync_redis(), hours=1, now=now)
    waits = report["queue_wait_seconds"]
    for queue, target in (("digest", DIGEST_WAIT_P95_SECONDS), ("embed", EMBED_WAIT_P95_SECONDS)):
        stats = waits.get(queue) or {}
        if stats.get("count", 0) >= MIN_SAMPLES and (stats.get("p95") or 0) > target:
            alerts.append(
                Alert(
                    f"queue_lag:{queue}",
                    f"{queue} queue wait p95 is {stats['p95']:.0f}s (target < {target}s).",
                )
            )
    delivery = report["digest_delivery"]
    ratio = delivery.get("on_time_ratio")
    if ratio is not None and delivery["lateness_seconds"]["count"] >= MIN_SAMPLES:
        if ratio < DIGEST_ON_TIME_TARGET:
            alerts.append(
                Alert("digest_late", f"Only {ratio:.0%} of digests were on time in the last hour.")
            )

    # API 5xx rate, last hour.
    hour = hour_key(now)
    total = await _count(redis, HTTP_COUNT_KEY.format(kind="all", hour=hour))
    errors = await _count(redis, HTTP_COUNT_KEY.format(kind="5xx", hour=hour))
    if total >= MIN_SAMPLES and errors / total > s.alert_5xx_rate:
        alerts.append(
            Alert("http_5xx", f"{errors} of {total} API requests failed (5xx) this hour.")
        )

    # LLM error rate, last hour.
    ok = await _count(redis, LLM_CALLS_KEY.format(outcome="ok", hour=hour))
    bad = await _count(redis, LLM_CALLS_KEY.format(outcome="error", hour=hour))
    if ok + bad >= 5 and bad / (ok + bad) > s.alert_llm_error_rate:
        alerts.append(Alert("llm_errors", f"{bad} of {ok + bad} LLM calls failed this hour."))

    # Disk.
    for path in [p.strip() for p in s.alert_disk_paths.split(",") if p.strip()]:
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        percent = usage.used / usage.total * 100 if usage.total else 0
        if percent > s.alert_disk_percent:
            alerts.append(Alert(f"disk:{path}", f"Disk {path} is {percent:.0f}% full."))

    # Backups.
    last_backup = await redis.get(BACKUP_KEY)
    if last_backup is not None and s.alert_backup_max_age_hours > 0:
        age_h = (now - float(last_backup)) / 3600
        if age_h > s.alert_backup_max_age_hours:
            alerts.append(Alert("backup", f"The last successful backup was {age_h:.0f} hours ago."))

    # Subscriptions that account deletion couldn't cancel (#221), last 7 days.
    from datetime import UTC, datetime, timedelta

    from app.models.billing import BillingEvent

    failed = (
        (
            await session.execute(
                select(BillingEvent.outcome).where(
                    BillingEvent.event_type == "account_deleted_cancel",
                    BillingEvent.outcome.like("failed:%"),
                    BillingEvent.received_at
                    >= datetime.fromtimestamp(now, UTC) - timedelta(days=7),
                )
            )
        )
        .scalars()
        .all()
    )
    if failed:
        subs = ", ".join(o.split("subscription ", 1)[-1] for o in failed)
        alerts.append(
            Alert(
                "billing_cancel_failed",
                f"Deleted accounts still have subscriptions to cancel by hand: {subs}.",
            )
        )

    # Stopped workers or scheduler (#234).
    for problem in await instance_health.check(session, now=now, redis=redis):
        if problem["key"].startswith(("beat", "worker:")):
            alerts.append(Alert(problem["key"], problem["message"]))
    return alerts


async def _notify(subject: str, body: str) -> int:
    import httpx

    from app.utils.email import send_email

    s = get_settings()
    sent = 0
    if s.alert_ntfy_url:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    s.alert_ntfy_url, content=body.encode(), headers={"Title": subject}
                )
            sent += resp.status_code < 400
        except httpx.HTTPError as e:
            logger.warning(f"ntfy alert failed: {type(e).__name__}")
    if s.alert_email:
        # Operator mail, not a reader email: no may_email / unsubscribe.
        sent += await send_email(
            to=s.alert_email,
            subject=subject,
            html_body=f"<pre>{body}</pre>",
            text_body=body,
        )
    return sent


async def run(session: AsyncSession, *, now: float | None = None, redis=None) -> dict:
    """Evaluate, then notify on new, repeating and resolved alerts."""
    from app.utils.cache import get_redis

    s = get_settings()
    now = now or time.time()
    redis = redis or get_redis()
    current = {a.key: a for a in await evaluate(session, now=now, redis=redis)}
    active = await redis.hgetall(ACTIVE_KEY)
    repeat = s.alert_repeat_hours * 3600
    instance = s.frontend_url
    out = {"firing": sorted(current), "sent": [], "resolved": []}

    for key, alert in current.items():
        first, last = (float(x) for x in (active.get(key) or f"{now},0").split(","))
        if last and now - last < repeat:
            continue
        sent = await _notify(
            f"[Weirling] {alert.message}", f"{alert.message}\n\nInstance: {instance}"
        )
        if sent or not (s.alert_ntfy_url or s.alert_email):
            await redis.hset(ACTIVE_KEY, key, f"{first},{now}")
            out["sent"].append(key)
    for key in set(active) - set(current):
        await _notify(f"[Weirling] Resolved: {key}", f"Resolved: {key}\n\nInstance: {instance}")
        await redis.hdel(ACTIVE_KEY, key)
        out["resolved"].append(key)
    if out["sent"] or out["resolved"]:
        logger.info(f"Alerts: firing={out['firing']} sent={out['sent']} resolved={out['resolved']}")
    return out
