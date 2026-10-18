"""Hosted billing through a merchant of record (#173).

A merchant of record (Lemon Squeezy or Paddle) sells the subscription, so the
operator does not register for VAT/GST in every buyer's country. ReadPrism
only reacts to the provider's signed webhooks:

- `users.tier` is what was bought ("pro" or "team"); `plan_expires_at` is
  when it lapses. `effective_plan()` combines them with the trial, so an
  expired subscription downgrades itself without a sweep job.
- Every event is recorded in `billing_events` once; a replay is a no-op.
  Events older than the last one applied to the user are recorded but not
  applied, so out-of-order delivery can't resurrect a cancelled plan.
- The tier comes only from the configured price/variant ids, never from
  anything the buyer can put in a checkout URL.

Self-hosted instances never see any of this: `effective_plan` is "selfhost".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.billing import BillingEvent
from app.models.user import User
from app.utils.logging import get_logger

logger = get_logger(__name__)

PAID_TIERS = ("pro", "team")
# Provider subscription statuses, normalised.
ACTIVE = "active"  # paid and current
TRIALING = "trialing"  # provider-side trial (counts as paid access)
PAST_DUE = "past_due"  # payment failed; the provider is retrying (dunning)
CANCELLED = "cancelled"  # will not renew; access until period end
ENDED = "ended"  # expired, refunded, paused, or cancelled immediately


@dataclass
class BillingUpdate:
    """One provider webhook, normalised."""

    provider: str
    key: str  # unique per event
    event_type: str
    occurred_at: datetime
    status: str | None = None  # one of the constants above; None = nothing to apply
    user_id: uuid.UUID | None = None
    customer_id: str | None = None
    subscription_id: str | None = None
    price_id: str | None = None
    period_end: datetime | None = None
    portal_url: str | None = None


def billing_enabled() -> bool:
    s = get_settings()
    return s.deployment_mode == "hosted" and bool(s.billing_provider)


def _ids(raw: str) -> set[str]:
    return {part.strip() for part in raw.split(",") if part.strip()}


def tier_for_price(price_id: str | None) -> str | None:
    s = get_settings()
    if price_id is None:
        return None
    if str(price_id) in _ids(s.billing_team_price_ids):
        return "team"
    if str(price_id) in _ids(s.billing_pro_price_ids):
        return "pro"
    return None


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def effective_plan(user: User, *, now: datetime | None = None) -> str:
    """ "selfhost" | "team" | "pro" | "trial" | "free"."""
    if get_settings().deployment_mode != "hosted":
        return "selfhost"
    now = now or datetime.now(UTC)
    expires = _aware(user.plan_expires_at)
    if user.tier in PAID_TIERS and (expires is None or expires > now):
        return user.tier
    trial = _aware(user.trial_ends_at)
    if trial is not None and trial > now:
        return "trial"
    return "free"


def start_trial(user: User, *, now: datetime | None = None) -> None:
    """New hosted accounts get the configured trial; no card needed."""
    days = get_settings().billing_trial_days
    if get_settings().deployment_mode == "hosted" and days > 0 and user.trial_ends_at is None:
        user.trial_ends_at = (now or datetime.now(UTC)) + timedelta(days=days)


async def _find_user(session: AsyncSession, update: BillingUpdate) -> User | None:
    if update.user_id is not None:
        user = await session.get(User, update.user_id)
        if user is not None:
            return user
    clauses = []
    if update.subscription_id:
        clauses.append(User.billing_subscription_id == update.subscription_id)
    if update.customer_id:
        clauses.append(User.billing_customer_id == update.customer_id)
    if not clauses:
        return None
    return (await session.execute(select(User).where(or_(*clauses)).limit(1))).scalar_one_or_none()


def _apply(user: User, update: BillingUpdate, now: datetime) -> None:
    s = get_settings()
    user.billing_provider = update.provider
    user.billing_customer_id = update.customer_id or user.billing_customer_id
    user.billing_subscription_id = update.subscription_id or user.billing_subscription_id
    user.billing_portal_url = update.portal_url or user.billing_portal_url
    user.billing_status = update.status
    user.billing_event_at = update.occurred_at
    if update.status == ENDED:
        user.tier = "free"
        user.plan_expires_at = now
        return
    tier = tier_for_price(update.price_id)
    if tier is not None:
        user.tier = tier
    elif user.tier not in PAID_TIERS:
        logger.warning(f"Billing event {update.key}: unknown price id {update.price_id!r}")
        return
    end = update.period_end
    if update.status == PAST_DUE and end is not None:
        end = max(end, now) + timedelta(days=s.billing_past_due_grace_days)
    user.plan_expires_at = end
    if update.status in (ACTIVE, TRIALING):
        user.trial_ends_at = None  # converted; the paid plan governs access now


async def apply_update(session: AsyncSession, update: BillingUpdate) -> str:
    """Apply one webhook. Returns "applied" | "duplicate" | "stale" | "ignored" | "unknown_user"."""
    now = datetime.now(UTC)
    user = await _find_user(session, update) if update.status else None
    if update.status is None:
        outcome = "ignored"
    elif user is None:
        outcome = "unknown_user"
    elif (last := _aware(user.billing_event_at)) is not None and update.occurred_at < last:
        outcome = "stale"
    else:
        outcome = "applied"
    inserted = (
        await session.execute(
            insert(BillingEvent)
            .values(
                key=update.key,
                provider=update.provider,
                event_type=update.event_type,
                user_id=user.id if user else None,
                outcome=outcome,
            )
            .on_conflict_do_nothing()
            .returning(BillingEvent.key)
        )
    ).scalar_one_or_none()
    if inserted is None:
        return "duplicate"
    if outcome == "applied" and user is not None:
        _apply(user, update, now)
    elif outcome == "unknown_user":
        logger.warning(f"Billing event {update.key} matches no account")
    await session.flush()
    return outcome


def provider(name: str | None = None):
    from app.services.billing import lemonsqueezy, paddle

    providers = {"lemonsqueezy": lemonsqueezy, "paddle": paddle}
    chosen = (name or get_settings().billing_provider or "").strip().lower()
    return providers.get(chosen)
