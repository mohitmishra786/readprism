"""Cold-start funnel, cohort retention, and the suggestion-read North Star.

The whole retention/PMF thesis was narrative and unmeasured. These aggregates are
computed directly from the tables that already record the events (users,
digests, user_content_interactions, sources) — no separate event pipeline to
keep in sync (audit 17-1/17-2/17-3, 16-1/16-2/16-4).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import UserContentInteraction
from app.models.digest import Digest
from app.models.source import Source
from app.models.user import User


async def suggestion_read_rate(session: AsyncSession, days: int = 30) -> dict:
    """North Star (audit 17-3): share of opened items that were *suggested*
    (read from a source the user didn't follow) — the purest signal that the
    discovery flywheel is turning."""
    since = datetime.now(UTC) - timedelta(days=days)
    opened = UserContentInteraction.opened_at.is_not(None)
    total = (
        await session.execute(
            select(func.count()).where(opened, UserContentInteraction.created_at >= since)
        )
    ).scalar() or 0
    suggested = (
        await session.execute(
            select(func.count()).where(
                opened,
                UserContentInteraction.was_suggested.is_(True),
                UserContentInteraction.created_at >= since,
            )
        )
    ).scalar() or 0
    return {
        "window_days": days,
        "opened_reads": total,
        "suggested_reads": suggested,
        "suggestion_read_rate": (suggested / total) if total else None,
    }


async def cold_start_funnel(session: AsyncSession) -> dict:
    """Signup → onboarded → opened a first digest → active in the last 7 days."""
    signed_up = (await session.execute(select(func.count()).select_from(User))).scalar() or 0
    onboarded = (
        await session.execute(
            select(func.count()).select_from(User).where(User.onboarding_complete.is_(True))
        )
    ).scalar() or 0
    opened_digest = (
        await session.execute(
            select(func.count(func.distinct(Digest.user_id))).where(Digest.opened.is_(True))
        )
    ).scalar() or 0
    recent = datetime.now(UTC) - timedelta(days=7)
    active_7d = (
        await session.execute(
            select(func.count(func.distinct(Digest.user_id))).where(
                Digest.opened.is_(True), Digest.generated_at >= recent
            )
        )
    ).scalar() or 0

    def pct(n: int) -> float | None:
        return (n / signed_up) if signed_up else None

    return {
        "signed_up": signed_up,
        "onboarded": onboarded,
        "opened_first_digest": opened_digest,
        "active_last_7d": active_7d,
        "onboarded_rate": pct(onboarded),
        "activation_rate": pct(opened_digest),
    }


async def cohort_retention(session: AsyncSession) -> list[dict]:
    """Per signup-week cohort: D1/D7/D30 retention (opened a digest at least that
    many days after signup)."""
    # Pull minimal per-user data and bucket in Python — simpler and portable than
    # a window-function SQL and fine at the scales this product targets.
    users = list((await session.execute(select(User.id, User.created_at))).all())
    if not users:
        return []

    # Map user -> latest opened-digest timestamp.
    opened_rows = (
        await session.execute(
            select(Digest.user_id, func.max(Digest.generated_at))
            .where(Digest.opened.is_(True))
            .group_by(Digest.user_id)
        )
    ).all()
    last_open = dict(opened_rows)

    cohorts: dict[str, list] = {}
    for uid, created in users:
        created = created if created.tzinfo else created.replace(tzinfo=UTC)
        week = created.strftime("%G-W%V")
        cohorts.setdefault(week, []).append((created, last_open.get(uid)))

    def retained(members: list, days: int) -> int:
        cutoff = timedelta(days=days)
        return sum(
            1
            for created, last in members
            if last is not None
            and (last if last.tzinfo else last.replace(tzinfo=UTC)) - created >= cutoff
        )

    out = []
    for week in sorted(cohorts):
        members = cohorts[week]
        n = len(members)
        out.append(
            {
                "cohort": week,
                "users": n,
                "d1": retained(members, 1) / n if n else None,
                "d7": retained(members, 7) / n if n else None,
                "d30": retained(members, 30) / n if n else None,
            }
        )
    return out


async def scraper_health(session: AsyncSession) -> dict:
    """Aggregate source-fetch health (audit 16-4/17-5): share of sources fetching
    cleanly vs degraded/failing."""
    total = (await session.execute(select(func.count()).select_from(Source))).scalar() or 0
    if total == 0:
        return {"total_sources": 0, "healthy": 0, "degraded": 0, "failing": 0, "success_rate": None}
    healthy = (
        await session.execute(
            select(func.count()).select_from(Source).where(Source.fetch_error_count == 0)
        )
    ).scalar() or 0
    failing = (
        await session.execute(
            select(func.count()).select_from(Source).where(Source.fetch_error_count >= 3)
        )
    ).scalar() or 0
    degraded = total - healthy - failing
    return {
        "total_sources": total,
        "healthy": healthy,
        "degraded": degraded,
        "failing": failing,
        "success_rate": healthy / total,
    }


async def email_deliverability() -> dict:
    """Email delivery success rate from the send-path counters (audit 17-6).

    Complaint/bounce rate requires a provider webhook (Resend/Mailgun), which is
    not wired up; reported as null until that exists.
    """
    from app.utils.cache import get_redis

    redis = get_redis()
    try:
        delivered = int(await redis.get("email:delivered") or 0)
        failed = int(await redis.get("email:failed") or 0)
    except Exception:
        delivered, failed = 0, 0
    total = delivered + failed
    return {
        "delivered": delivered,
        "failed": failed,
        "delivery_rate": (delivered / total) if total else None,
        "complaint_rate": None,  # needs a provider bounce/complaint webhook
    }


async def meta_weight_divergence(session: AsyncSession) -> dict:
    """Mean divergence of learned weights from defaults (audit 16-7): a proxy for
    how much personalization has actually happened."""
    from app.models.meta_weights import UserMetaWeights as MW
    from app.services.ranking.meta_weights import DEFAULT_WEIGHTS

    rows = list((await session.execute(select(MW.weights))).scalars())
    if not rows:
        return {"users_with_learned_weights": 0, "mean_abs_divergence": None}
    divs = []
    for weights in rows:
        d = sum(abs(weights.get(k, v) - v) for k, v in DEFAULT_WEIGHTS.items())
        divs_val = d / len(DEFAULT_WEIGHTS)
        divs.append(divs_val)
    return {
        "users_with_learned_weights": len(divs),
        "mean_abs_divergence": sum(divs) / len(divs),
    }
