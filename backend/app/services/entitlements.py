"""Plan entitlements: per-plan quotas on hosted (#109, #172).

ReadPrism runs in one of two deployment modes (`DEPLOYMENT_MODE`):

- `selfhost` (default): the instance owner's server. No plans, no quotas,
  never an "upgrade" message. Only a short guard against double-clicking
  "generate digest".
- `hosted`: the managed service. Each plan (free, trial, pro, team) has the
  quotas in `DEFAULT_PLAN_QUOTAS`, merged with `HOSTED_PLAN_QUOTAS`, and an
  admin can override them per account (`users.quota_overrides`). These gate
  *quantity*, never the ranking engine itself (audit 13-1/13-5).

Every plan check in the app goes through this module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import DEFAULT_PLAN_QUOTAS, get_settings
from app.models.user import User

settings = get_settings()

HOSTED = "hosted"
SELFHOST = "selfhost"

# Account totals.
SOURCES = "sources"
CREATORS = "creators"
# Daily allowances (UTC day), counted in Redis.
NEWSLETTERS = "newsletters_per_day"
NEWSLETTER_MB = "newsletter_mb_per_day"
LLM_SUMMARIES = "llm_summaries_per_day"
DIGEST_BUILDS = "digest_builds_per_day"
QUOTAS = (SOURCES, CREATORS, NEWSLETTERS, NEWSLETTER_MB, LLM_SUMMARIES, DIGEST_BUILDS)
DAILY = (NEWSLETTERS, NEWSLETTER_MB, LLM_SUMMARIES, DIGEST_BUILDS)


def is_hosted() -> bool:
    return settings.deployment_mode == HOSTED


def _plan(user: User) -> str:
    from app.services.billing import effective_plan

    return effective_plan(user)


def plan_quotas(plan: str) -> dict[str, int]:
    """The configured quotas of one plan; 0 = unlimited."""
    row = {q: 0 for q in QUOTAS}
    if plan == "free":
        row[SOURCES] = settings.free_max_sources
        row[CREATORS] = settings.free_max_creators
    row.update(DEFAULT_PLAN_QUOTAS.get(plan, {}))
    row.update(settings.hosted_plan_quotas.get(plan, {}))
    return row


def limit(user: User, quota: str) -> int:
    """This account's limit for `quota`; 0 = unlimited (always on self-host)."""
    if not is_hosted():
        return 0
    override = (user.quota_overrides or {}).get(quota)
    if override is not None:
        return int(override)
    return plan_quotas(_plan(user))[quota]


def _upgrade_hint(user: User) -> str:
    plan = _plan(user)
    if plan in ("free", "trial"):
        return " Subscribe to raise it."
    if plan == "pro":
        return " The Team plan raises it."
    return " Contact support to raise it."


# ------------------------------------------------------------ account totals


def enforce_source_limit(user: User, current_count: int, adding: int = 1) -> None:
    """Raise 402 if adding `adding` sources would exceed the user's plan."""
    cap = limit(user, SOURCES)
    if cap > 0 and current_count + adding > cap:
        remaining = max(0, cap - current_count)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Your plan includes {cap} sources and you have {current_count}"
                + (f"; you can add {remaining} more." if remaining else ".")
                + _upgrade_hint(user)
            ),
        )


def enforce_creator_limit(user: User, current_count: int, adding: int = 1) -> None:
    """Raise 402 if adding `adding` creators would exceed the user's plan."""
    cap = limit(user, CREATORS)
    if cap > 0 and current_count + adding > cap:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Your plan includes {cap} tracked creators." + _upgrade_hint(user),
        )


# ---------------------------------------------------------- daily allowances


def _day_key(user_id: uuid.UUID | str, quota: str) -> str:
    return f"quota:{quota}:{user_id}:{datetime.now(UTC):%Y%m%d}"


def _amount(quota: str, amount: int) -> int:
    # Newsletter volume is counted in bytes, limited in MB.
    return amount * 1_000_000 if quota == NEWSLETTER_MB else amount


async def used_today(user_id: uuid.UUID | str, quota: str) -> int:
    from app.utils.cache import get_redis

    try:
        value = await get_redis().get(_day_key(user_id, quota))
    except Exception:
        return 0
    return int(value or 0)


async def remaining_today(user: User, quota: str) -> int | None:
    """What is left of a daily allowance today; None = unlimited."""
    cap = limit(user, quota)
    if cap <= 0:
        return None
    return max(0, _amount(quota, cap) - await used_today(user.id, quota))


async def record_use(user: User, quota: str, amount: int = 1) -> None:
    """Count `amount` against a daily allowance (bytes for newsletter MB)."""
    if amount == 0 or limit(user, quota) <= 0:
        return
    from app.utils.cache import cache_incr

    await cache_incr(_day_key(user.id, quota), amount, ttl_seconds=2 * 86400)


async def take(user: User, quota: str, amount: int = 1) -> bool:
    """Count `amount` if it fits today's allowance; False (nothing counted) if not.

    Fails open when Redis is unreachable, like the abuse counters.
    """
    cap = limit(user, quota)
    if cap <= 0:
        return True
    from app.utils.cache import cache_incr

    key = _day_key(user.id, quota)
    used = await cache_incr(key, amount, ttl_seconds=2 * 86400)
    if used is None or used <= _amount(quota, cap):
        return True
    await cache_incr(key, -amount, ttl_seconds=2 * 86400)
    return False


async def newsletter_allowed(user: User, size_bytes: int) -> tuple[bool, str]:
    """(allowed, reason) for one inbound newsletter, against the plan's daily quota."""
    if not await take(user, NEWSLETTERS):
        return False, "plan's daily newsletter count reached"
    if not await take(user, NEWSLETTER_MB, size_bytes):
        await record_use(user, NEWSLETTERS, -1)
        return False, "plan's daily newsletter volume reached"
    return True, ""


def daily_quota_message(user: User, quota: str) -> str:
    cap = limit(user, quota)
    what = {
        DIGEST_BUILDS: f"{cap} digest builds a day",
        LLM_SUMMARIES: f"{cap} AI summaries a day",
        NEWSLETTERS: f"{cap} newsletters a day",
        NEWSLETTER_MB: f"{cap} MB of newsletters a day",
    }[quota]
    return f"Your plan includes {what}; it resets at midnight UTC." + _upgrade_hint(user)


async def usage(session: AsyncSession, user: User) -> list[dict]:
    """Limits and use for the plan screen; empty on self-host."""
    if not is_hosted():
        return []
    from app.models.creator import Creator
    from app.models.source import Source

    totals = {}
    for quota, model in ((SOURCES, Source), (CREATORS, Creator)):
        totals[quota] = (
            await session.execute(
                select(func.count()).select_from(model).where(model.user_id == user.id)
            )
        ).scalar_one()
    rows = []
    for quota in QUOTAS:
        count = totals[quota] if quota in totals else await used_today(user.id, quota)
        used: float = round(count / 1_000_000, 1) if quota == NEWSLETTER_MB else count
        rows.append(
            {"quota": quota, "limit": limit(user, quota), "used": used, "daily": quota in DAILY}
        )
    return rows


# ------------------------------------------------------------ manual digests


def digest_regeneration_window(user: User) -> timedelta:
    """Minimum time between manual digest generations for this user."""
    if is_hosted() and _plan(user) == "free":
        return timedelta(minutes=settings.hosted_free_digest_regen_minutes)
    return timedelta(seconds=settings.manual_digest_guard_seconds)


def digest_regeneration_message(user: User) -> str:
    if is_hosted() and _plan(user) == "free":
        minutes = settings.hosted_free_digest_regen_minutes
        return f"Your plan allows one manual digest every {minutes} minutes."
    return "A digest is already being built. Try again in a minute."
