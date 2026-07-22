"""Lapsed-user win-back emails (audit 10-5).

The only retention channel is the daily digest; when a user stops opening it,
nothing brings them back. This task finds users who haven't opened a digest in
`reengagement_inactivity_days` and haven't already been nudged within the
cooldown, and sends one short win-back email.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.utils.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


def _reengagement_email_html(frontend_url: str, unsubscribe: str) -> str:
    return (
        '<div style="font-family:sans-serif;max-width:520px;margin:0 auto;color:#111827">'
        '<h1 style="font-size:1.3rem;color:#1d4ed8">Your reading has been piling up</h1>'
        "<p>It's been a little while. ReadPrism has kept ranking your sources by "
        "personal relevance — your next digest is ready when you are.</p>"
        f'<p><a href="{frontend_url}/digest" style="display:inline-block;background:#1d4ed8;'
        'color:#fff;padding:10px 18px;border-radius:6px;text-decoration:none">'
        "See what you missed</a></p>"
        f'<p style="font-size:12px;color:#9ca3af;margin-top:24px">'
        f'<a href="{unsubscribe}" style="color:#9ca3af">Unsubscribe</a></p></div>'
    )


async def _run() -> dict:
    from sqlalchemy import func, select

    from app.database import AsyncSessionLocal
    from app.models.digest import Digest
    from app.models.user import User
    from app.utils.cache import cache_exists, cache_set
    from app.utils.email import send_email
    from app.utils.unsubscribe import unsubscribe_url

    settings = get_settings()
    now = datetime.now(UTC)
    inactive_cutoff = now - timedelta(days=settings.reengagement_inactivity_days)

    async with AsyncSessionLocal() as session:
        # Candidate users: onboarded, email delivery on, signed up before the
        # inactivity window (not brand-new).
        users = list(
            (
                await session.execute(
                    select(User).where(
                        User.onboarding_complete.is_(True),
                        User.digest_frequency != "in_app_only",
                        User.created_at <= inactive_cutoff,
                    )
                )
            ).scalars()
        )

        # Last opened-digest time per user.
        opened = dict(
            (
                await session.execute(
                    select(Digest.user_id, func.max(Digest.generated_at))
                    .where(Digest.opened.is_(True))
                    .group_by(Digest.user_id)
                )
            ).all()
        )

        sent = 0
        for user in users:
            last = opened.get(user.id)
            if last is not None:
                last = last if last.tzinfo else last.replace(tzinfo=UTC)
                if last >= inactive_cutoff:
                    continue  # still active
            cooldown_key = f"reengagement:sent:{user.id}"
            if await cache_exists(cooldown_key):
                continue
            html = _reengagement_email_html(
                settings.frontend_url.rstrip("/"), unsubscribe_url(user.id)
            )
            ok = await send_email(
                to=user.email,
                subject="Your ReadPrism reading is piling up",
                html_body=html,
                extra_headers={
                    "List-Unsubscribe": f"<{unsubscribe_url(user.id)}>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                },
            )
            if ok:
                await cache_set(
                    cooldown_key, 1, ttl_seconds=settings.reengagement_cooldown_days * 86400
                )
                sent += 1

    logger.info(f"Sent {sent} re-engagement emails")
    return {"sent": sent}


@celery_app.task(name="app.workers.tasks.reengagement.send_reengagement_emails")
def send_reengagement_emails() -> dict:
    return asyncio.run(_run())
