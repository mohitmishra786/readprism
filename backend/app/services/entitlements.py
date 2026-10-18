"""Plan entitlements: quantity limits and manual-digest throttling (#109).

ReadPrism runs in one of two deployment modes (`DEPLOYMENT_MODE`):

- `selfhost` (default): the instance owner's server. No plans, no quotas,
  never an "upgrade" message. Only a short guard against double-clicking
  "generate digest".
- `hosted`: the managed service. Users on the `free` tier get the configured
  quantity limits; any other tier is unlimited. These gate *quantity*, never
  the ranking engine itself (audit 13-1/13-5).

Every tier check in the app goes through this module.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException, status

from app.config import get_settings
from app.models.user import User

settings = get_settings()

HOSTED = "hosted"
SELFHOST = "selfhost"


def is_hosted() -> bool:
    return settings.deployment_mode == HOSTED


def _is_free(user: User) -> bool:
    return (user.tier or "free") == "free"


def _limited(user: User) -> bool:
    """Quota limits apply only to free-tier users of the hosted service."""
    return is_hosted() and _is_free(user)


def enforce_source_limit(user: User, current_count: int, adding: int = 1) -> None:
    """Raise 402 if adding `adding` sources would exceed the user's plan."""
    limit = settings.free_max_sources
    if _limited(user) and limit > 0 and current_count + adding > limit:
        remaining = max(0, limit - current_count)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Your plan includes {limit} sources and you have {current_count}"
                + (f"; you can add {remaining} more." if remaining else ".")
                + " Upgrade your plan to add more."
            ),
        )


def enforce_creator_limit(user: User, current_count: int, adding: int = 1) -> None:
    """Raise 402 if adding `adding` creators would exceed the user's plan."""
    limit = settings.free_max_creators
    if _limited(user) and limit > 0 and current_count + adding > limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Your plan includes {limit} tracked creators. Upgrade your plan to track more."
            ),
        )


def digest_regeneration_window(user: User) -> timedelta:
    """Minimum time between manual digest generations for this user."""
    if _limited(user):
        return timedelta(minutes=settings.hosted_free_digest_regen_minutes)
    return timedelta(seconds=settings.manual_digest_guard_seconds)


def digest_regeneration_message(user: User) -> str:
    if _limited(user):
        minutes = settings.hosted_free_digest_regen_minutes
        return f"Your plan allows one manual digest every {minutes} minutes."
    return "A digest is already being built. Try again in a minute."
