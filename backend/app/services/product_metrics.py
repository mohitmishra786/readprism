"""First-party product metrics and the North Star dashboard (D-20, #131).

No third-party SDKs and nothing leaves the server. On by default for hosted,
off for self-host (PRODUCT_METRICS). Raw events are kept for the life of the
account and deleted with it; daily totals (no user ids) are kept for trends.

North Star: Weekly Satisfied Readers (WSR), readers who in a 7-day window
opened at least 3 digests and finished (≥ 70% read) at least 3 items.
Input metrics (PRODUCT_PLAN §1): time to first good digest, interleaving win
rate, D7/D30 retention, top-5 precision (self-reported) and feed health.
"""

from __future__ import annotations

import statistics
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

EVENTS = (
    "signup",
    "onboarding_finished",
    "source_added",
    "digest_sent",
    "digest_opened",
    "item_opened",
    "item_finished",
    "rating",
    "save",
    "trial_converted",
    "cancel",
    "top5_rating",
)
FINISHED = 0.7  # the North Star's "fully read" (composite completion)

# Targets from PRODUCT_PLAN §1, shown next to each value.
TARGETS = {
    "ttfgd_minutes_median": "< 10 hosted, < 20 self-host",
    "interleaving_win_rate": ">= 0.55",
    "retention_d7": ">= 0.60",
    "retention_d30": ">= 0.40",
    "top5_wanted_median": ">= 3",
    "feed_health": ">= 0.95",
}


def enabled() -> bool:
    setting = get_settings().product_metrics.strip().lower()
    if setting in ("on", "true", "1"):
        return True
    if setting in ("off", "false", "0"):
        return False
    return get_settings().deployment_mode == "hosted"


async def track(session: AsyncSession, user_id: uuid.UUID | None, event: str, **props: Any) -> None:
    """Record one event in the caller's transaction. Never raises."""
    if user_id is None or not enabled():
        return
    if event not in EVENTS:
        logger.warning(f"Unknown product event {event!r}")
        return
    try:
        from app.models.product_event import ProductEvent

        session.add(ProductEvent(user_id=user_id, event=event, props=props))
    except Exception as e:  # metrics must never break the product
        logger.warning(f"Product event {event} not recorded: {e}")


def snapshot(interaction) -> dict | None:
    """The fields interaction_events compares, before an update."""
    if interaction is None:
        return None
    return {
        "opened_at": interaction.opened_at,
        "completion": interaction.read_completion_pct,
        "rating": interaction.explicit_rating,
        "saved": bool(interaction.saved),
    }


def interaction_events(before: dict | None, after) -> list[tuple[str, dict]]:
    """Events implied by one interaction update: only real transitions count."""
    b = before or {}
    events: list[tuple[str, dict]] = []
    if after.opened_at and not b.get("opened_at"):
        events.append(("item_opened", {}))
    if (after.read_completion_pct or 0) >= FINISHED and (b.get("completion") or 0) < FINISHED:
        events.append(("item_finished", {}))
    if after.explicit_rating and after.explicit_rating != b.get("rating"):
        events.append(("rating", {"value": int(after.explicit_rating)}))
    if after.saved and not b.get("saved"):
        events.append(("save", {}))
    return events


async def track_interaction(session: AsyncSession, before: dict | None, after) -> None:
    for event, props in interaction_events(before, after):
        await track(session, after.user_id, event, **props)


# ------------------------------------------------------------------ metrics


async def _events(session, event: str, since: datetime, until: datetime) -> list:
    from app.models.product_event import ProductEvent

    return (
        await session.execute(
            select(ProductEvent.user_id, ProductEvent.created_at, ProductEvent.props).where(
                ProductEvent.event == event,
                ProductEvent.created_at >= since,
                ProductEvent.created_at < until,
            )
        )
    ).all()


async def weekly_satisfied_readers(session, now: datetime) -> int:
    since = now - timedelta(days=7)
    opened: dict[uuid.UUID, int] = {}
    finished: dict[uuid.UUID, int] = {}
    for uid, _, _ in await _events(session, "digest_opened", since, now):
        opened[uid] = opened.get(uid, 0) + 1
    for uid, _, _ in await _events(session, "item_finished", since, now):
        finished[uid] = finished.get(uid, 0) + 1
    return sum(1 for uid, n in opened.items() if n >= 3 and finished.get(uid, 0) >= 3)


async def ttfgd_minutes_median(session, now: datetime) -> float | None:
    """Sign-up to the first digest with ≥ 5 items across ≥ 3 topics, for the
    last 30 days' sign-ups (from the digests themselves, not events)."""
    from app.models.content import ContentItem
    from app.models.digest import Digest, DigestItem
    from app.models.user import User

    users = (
        await session.execute(
            select(User.id, User.created_at).where(User.created_at >= now - timedelta(days=30))
        )
    ).all()
    minutes: list[float] = []
    for uid, created in users:
        digests = (
            await session.execute(
                select(Digest.id, Digest.generated_at)
                .where(Digest.user_id == uid, Digest.total_items >= 5)
                .order_by(Digest.generated_at)
                .limit(5)
            )
        ).all()
        for digest_id, generated in digests:
            topics = (
                await session.execute(
                    select(ContentItem.topic_clusters)
                    .join(DigestItem, DigestItem.content_item_id == ContentItem.id)
                    .where(DigestItem.digest_id == digest_id)
                )
            ).scalars()
            if len({(t or [""])[0] for t in topics if t}) >= 3:
                minutes.append((generated - created).total_seconds() / 60)
                break
    return round(statistics.median(minutes), 1) if minutes else None


async def retention(session, now: datetime, day: int) -> float | None:
    """Of readers who signed up 'day' to 'day'+30 days ago, the share who opened
    a digest during days day..day+6 after signing up."""
    signups = await _events(
        session, "signup", now - timedelta(days=day + 30), now - timedelta(days=day)
    )
    if not signups:
        return None
    kept = 0
    for uid, signed_up, _ in signups:
        start = signed_up + timedelta(days=day)
        opens = await _events(session, "digest_opened", start, start + timedelta(days=7))
        kept += any(o[0] == uid for o in opens)
    return round(kept / len(signups), 3)


async def top5_wanted_median(session, now: datetime) -> float | None:
    rows = await _events(session, "top5_rating", now - timedelta(days=30), now)
    values = [int(p.get("wanted", 0)) for _, _, p in rows if isinstance(p, dict)]
    return statistics.median(values) if values else None


async def feed_health(session) -> float | None:
    from app.models.feed import Feed

    total = (
        await session.execute(select(func.count(Feed.id)).where(Feed.is_active.is_(True)))
    ).scalar_one()
    if not total:
        return None
    healthy = (
        await session.execute(
            select(func.count(Feed.id)).where(
                Feed.is_active.is_(True), Feed.feed_status == "healthy"
            )
        )
    ).scalar_one()
    return round(healthy / total, 3)


async def interleaving_win_rate(session, now: datetime) -> float | None:
    from app.services.ranking.interleaving import interleaving_report

    report = await interleaving_report(session, days=7, now=now)
    return report["pooled"]["prs_win_rate"]


async def current(session: AsyncSession, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    return {
        "weekly_satisfied_readers": await weekly_satisfied_readers(session, now),
        "ttfgd_minutes_median": await ttfgd_minutes_median(session, now),
        "interleaving_win_rate": await interleaving_win_rate(session, now),
        "retention_d7": await retention(session, now, 7),
        "retention_d30": await retention(session, now, 30),
        "top5_wanted_median": await top5_wanted_median(session, now),
        "feed_health": await feed_health(session),
    }


async def event_counts(session, since: datetime, until: datetime) -> dict[str, int]:
    from app.models.product_event import ProductEvent

    rows = (
        await session.execute(
            select(ProductEvent.event, func.count())
            .where(ProductEvent.created_at >= since, ProductEvent.created_at < until)
            .group_by(ProductEvent.event)
        )
    ).all()
    counts = {event: 0 for event in EVENTS}
    counts.update(dict(rows))
    return counts


async def rollup(session: AsyncSession, day: date) -> dict[str, float | None]:
    """Store one day's event counts and the metrics as of the end of that day."""
    from app.models.product_event import ProductMetricDaily

    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    values: dict[str, float | None] = {
        f"events.{k}": float(v) for k, v in (await event_counts(session, start, end)).items()
    }
    for key, value in (await current(session, end)).items():
        values[key] = None if value is None else float(value)
    for metric, value in values.items():
        stmt = insert(ProductMetricDaily).values(day=day, metric=metric, value=value)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["day", "metric"], set_={"value": stmt.excluded.value}
            )
        )
    return values


async def dashboard(session: AsyncSession, days: int = 30) -> dict[str, Any]:
    from app.models.product_event import ProductMetricDaily

    now = datetime.now(UTC)
    since = (now - timedelta(days=days)).date()
    rows = (
        await session.execute(
            select(ProductMetricDaily.day, ProductMetricDaily.metric, ProductMetricDaily.value)
            .where(ProductMetricDaily.day >= since)
            .order_by(ProductMetricDaily.day)
        )
    ).all()
    series: dict[str, list] = {}
    for day, metric, value in rows:
        series.setdefault(metric, []).append({"day": day.isoformat(), "value": value})
    return {
        "enabled": enabled(),
        "now": await current(session, now),
        "targets": TARGETS,
        "events_last_30_days": await event_counts(session, now - timedelta(days=30), now),
        "series": series,
    }
