"""Tier entitlement checks (audit 13-1/13-5).

Tiers previously existed only as a `users.tier` field plus one digest-generation
throttle. This is server-side enforcement scaffolding for the quantity limits
(sources, creators). Limits are config-driven so the founder can set the final
Free/Pro structure without code changes; Pro (and any non-free tier) is
unlimited. The philosophically-right "ranking engine is free" is preserved —
these gate *quantity*, not the intelligence.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.config import get_settings
from app.models.user import User

settings = get_settings()


def _is_free(user: User) -> bool:
    return (user.tier or "free") == "free"


def enforce_source_limit(user: User, current_count: int) -> None:
    """Raise 402 if a free user is at their source limit."""
    limit = settings.free_max_sources
    if _is_free(user) and limit > 0 and current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Free tier is limited to {limit} sources. " "Upgrade to Pro for unlimited sources."
            ),
        )


def enforce_creator_limit(user: User, current_count: int) -> None:
    """Raise 402 if a free user is at their creator limit."""
    limit = settings.free_max_creators
    if _is_free(user) and limit > 0 and current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Free tier is limited to {limit} tracked creators. "
                "Upgrade to Pro for unlimited creators."
            ),
        )
