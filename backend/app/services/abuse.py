"""Hosted abuse controls: fetch budgets, per-host caps, inbound caps (#169).

A hosted account must not be able to turn the service into a scraping or
DoS proxy (thousands of feed URLs on one victim host) or flood the
newsletter inbox. All counters are fixed hourly or daily windows in Redis.
When Redis is unreachable the fetch checks fail open (ingestion keeps
running; per-host politeness still applies) and log a warning.

Self-hosted instances skip everything here except the per-message inbound
size cap, which protects any instance from a single oversized email.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _hosted() -> bool:
    return get_settings().deployment_mode == "hosted"


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _hour(now: datetime) -> str:
    return now.strftime("%Y%m%d%H")


def _next_hour(now: datetime) -> datetime:
    return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


# ----------------------------------------------------------------- fetch budget


async def charge_fetch(user_id: uuid.UUID, *, n: int = 1, now: datetime | None = None) -> bool:
    """Spend `n` fetches of this account's hourly budget; False if over it."""
    limit = get_settings().hosted_fetch_budget_per_hour
    if not _hosted() or limit <= 0:
        return True
    from app.utils.cache import cache_incr

    now = now or datetime.now(UTC)
    used = await cache_incr(f"fetchbudget:{user_id}:{_hour(now)}", n, ttl_seconds=7200)
    return used is None or used <= limit


async def charge_host_poll(url: str, *, now: datetime | None = None) -> bool:
    """One poll of this host across all accounts; False if the host is at its cap."""
    limit = get_settings().hosted_host_polls_per_hour
    host = host_of(url)
    if not _hosted() or limit <= 0 or not host:
        return True
    from app.utils.cache import cache_incr

    now = now or datetime.now(UTC)
    used = await cache_incr(f"hostpolls:{host}:{_hour(now)}", 1, ttl_seconds=7200)
    return used is None or used <= limit


async def pause_fetches(
    session: AsyncSession, user_ids: list[uuid.UUID], *, now: datetime | None = None
) -> datetime:
    """Record the pause so the app can tell the user; returns when it ends."""
    from app.models.user import User

    until = _next_hour(now or datetime.now(UTC))
    if user_ids:
        await session.execute(
            update(User)
            .where(User.id.in_(user_ids))
            .values(fetch_paused_until=until)
            .execution_options(synchronize_session=False)
        )
        logger.warning(f"Fetch budget exhausted for {len(user_ids)} account(s) until {until}")
    return until


async def require_fetch_budget(session: AsyncSession, user) -> None:
    """For on-demand fetches (add a source, refresh now): 429 when over budget."""
    if await charge_fetch(user.id):
        return
    until = await pause_fetches(session, [user.id])
    # Persist the notice: the error response rolls the request session back.
    await session.commit()
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=(
            "This account has used its hourly fetch budget. Fetching resumes at "
            f"{until.strftime('%H:%M')} UTC."
        ),
        headers={"Retry-After": str(int((until - datetime.now(UTC)).total_seconds()) + 1)},
    )


# ------------------------------------------------------------- sources per host


async def enforce_sources_per_host(session: AsyncSession, user, urls: list[str]) -> None:
    """422 when adding `urls` would put too many of this account's sources on one host."""
    limit = get_settings().hosted_max_sources_per_host
    if not _hosted() or limit <= 0 or not urls:
        return
    from app.models.source import Source

    existing = (
        await session.execute(select(Source.url, Source.feed_url).where(Source.user_id == user.id))
    ).all()
    counts: dict[str, int] = {}
    for url, feed_url in existing:
        host = host_of(feed_url or url)
        counts[host] = counts.get(host, 0) + 1
    for url in urls:
        host = host_of(url)
        if not host:
            continue
        counts[host] = counts.get(host, 0) + 1
        if counts[host] > limit:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"An account can follow at most {limit} feeds on {host}.",
            )


# --------------------------------------------------------------- inbound email


async def inbound_allowed(user_id: uuid.UUID | str | None, size_bytes: int) -> tuple[bool, str]:
    """(allowed, reason) for one inbound newsletter addressed to this user."""
    s = get_settings()
    if s.inbound_max_message_bytes > 0 and size_bytes > s.inbound_max_message_bytes:
        return False, "message too large"
    if not _hosted() or user_id is None:
        return True, ""
    from app.utils.cache import cache_incr

    day = datetime.now(UTC).strftime("%Y%m%d")
    if s.hosted_inbound_per_day > 0:
        count = await cache_incr(f"inbound:n:{user_id}:{day}", 1, ttl_seconds=2 * 86400)
        if count is not None and count > s.hosted_inbound_per_day:
            return False, "daily newsletter count reached"
    if s.hosted_inbound_mb_per_day > 0:
        used = await cache_incr(f"inbound:b:{user_id}:{day}", size_bytes, ttl_seconds=2 * 86400)
        if used is not None and used > s.hosted_inbound_mb_per_day * 1_000_000:
            return False, "daily newsletter volume reached"
    return True, ""
