"""Who may create an account on this instance (#153).

`REGISTRATION_MODE`:
- `closed`: only the first account (the instance owner) can register;
- `invite`: new accounts need a code from `REGISTRATION_INVITE_CODES`
  (comma-separated); the first account never needs one;
- `open`: anyone can register.

Default: `closed` in selfhost mode (an exposed self-hosted instance must not
let strangers spend its fetch capacity and LLM key), `open` on hosted.
"""

from __future__ import annotations

import hmac

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User

MODES = ("closed", "invite", "open")


def effective_mode() -> str:
    s = get_settings()
    mode = (s.registration_mode or "").strip().lower()
    if mode in MODES:
        return mode
    return "open" if s.deployment_mode == "hosted" else "closed"


def _valid_invite(code: str | None) -> bool:
    if not code:
        return False
    codes = [c.strip() for c in get_settings().registration_invite_codes.split(",") if c.strip()]
    return any(hmac.compare_digest(code.strip(), valid) for valid in codes)


async def _has_users(session: AsyncSession) -> bool:
    return bool((await session.execute(select(func.count(User.id)))).scalar())


async def can_register(session: AsyncSession, invite_code: str | None = None) -> tuple[bool, str]:
    """(allowed, reason-if-not)."""
    mode = effective_mode()
    if mode == "open" or not await _has_users(session):
        return True, ""
    if mode == "invite":
        if _valid_invite(invite_code):
            return True, ""
        return False, "A valid invite code is required to create an account here."
    return False, "Registration is closed on this instance. Ask its owner for an account."
