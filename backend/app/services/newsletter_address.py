"""Each user's personal newsletter address and its live test (#151).

Users forward or subscribe newsletters to ``u.<token>@<NEWSLETTER_DOMAIN>``.
The token is created on first use (nothing generated it before, so no user
had an address). "Send a test" mails a one-off marker to that address; when
the inbound webhook sees it, it records the arrival instead of storing it as
content, and the UI shows that the address works end to end.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User

TEST_SUBJECT_PREFIX = "Weirling address test "
TEST_TTL_SECONDS = 15 * 60
_DEFAULT_DOMAIN = "newsletters.weirling.local"


def _test_key(user_id: uuid.UUID | str) -> str:
    return f"newsletter-test:{user_id}"


async def ensure_token(user: User, session: AsyncSession) -> str:
    if not user.newsletter_token:
        user.newsletter_token = secrets.token_hex(6)  # 12 chars, lowercase-safe in addresses
        await session.flush()
    return user.newsletter_token


def address_for(token: str) -> str:
    return f"u.{token}@{get_settings().newsletter_domain}"


def inbound_configured() -> bool:
    """Is mail to the newsletter domain likely to reach this instance?"""
    s = get_settings()
    has_receiver = any(
        (
            s.mailgun_webhook_signing_key,
            s.postmark_webhook_secret,
            s.resend_webhook_secret,
            s.cloudflare_email_webhook_secret,
        )
    )
    return s.newsletter_domain != _DEFAULT_DOMAIN and has_receiver


async def start_test(user_id: uuid.UUID) -> str:
    from app.utils.cache import cache_set

    nonce = secrets.token_hex(4)
    await cache_set(
        _test_key(user_id),
        {"nonce": nonce, "sent_at": datetime.now(UTC).isoformat(), "received_at": None},
        ttl_seconds=TEST_TTL_SECONDS,
    )
    return nonce


async def test_status(user_id: uuid.UUID) -> dict:
    from app.utils.cache import cache_get

    state = await cache_get(_test_key(user_id))
    if not state:
        return {"status": "none"}
    return {
        "status": "received" if state.get("received_at") else "waiting",
        "sent_at": state.get("sent_at"),
        "received_at": state.get("received_at"),
    }


async def record_if_test(user_id: uuid.UUID | str | None, subject: str) -> bool:
    """True (and the arrival recorded) if this inbound mail is the user's test."""
    if user_id is None or not subject or TEST_SUBJECT_PREFIX not in subject:
        return False
    from app.utils.cache import cache_get, cache_set

    state = await cache_get(_test_key(user_id))
    if not state or state.get("nonce") not in subject:
        return False
    state["received_at"] = datetime.now(UTC).isoformat()
    await cache_set(_test_key(user_id), state, ttl_seconds=TEST_TTL_SECONDS)
    return True
