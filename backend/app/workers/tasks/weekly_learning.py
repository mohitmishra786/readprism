"""Weekly 'What I learned about you' emails (#184). Opt-in per user."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.utils.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

# Idempotent: one email per user per 6 days, whatever the beat does.
MIN_INTERVAL = timedelta(days=6)


async def _run(now: datetime | None = None) -> dict:
    from sqlalchemy import or_, select

    from app.config import get_settings
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.digest.weekly_learning import compute, render
    from app.services.email_verification import may_email
    from app.utils.email import send_email
    from app.utils.signed_links import topic_action_url
    from app.utils.unsubscribe import weekly_unsubscribe_url

    now = now or datetime.now(UTC)
    settings = get_settings()
    frontend = settings.frontend_url.rstrip("/")
    sent = skipped = 0
    async with AsyncSessionLocal() as session:
        users = (
            await session.execute(
                select(User).where(
                    User.weekly_email.is_(True),
                    or_(
                        User.weekly_email_sent_at.is_(None),
                        User.weekly_email_sent_at <= now - MIN_INTERVAL,
                    ),
                )
            )
        ).scalars()
        for user in list(users):
            if not may_email(user):
                skipped += 1
                continue
            learning = await compute(user, session, now)
            if learning.empty:
                skipped += 1
                continue
            links = {
                (t, "less"): topic_action_url(user.id, t, "less") for t, _, _ in learning.rising
            }
            if learning.fading:
                links[(learning.fading, "more")] = topic_action_url(
                    user.id, learning.fading, "more"
                )
            unsubscribe = weekly_unsubscribe_url(user.id)
            html_body, text_body = render(
                user, learning, links=links, frontend_url=frontend, unsubscribe=unsubscribe
            )
            ok = await send_email(
                to=user.email,
                subject="What ReadPrism learned about you this week",
                html_body=html_body,
                text_body=text_body,
                extra_headers={
                    "List-Unsubscribe": f"<{unsubscribe}>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                },
            )
            if ok:
                user.weekly_email_sent_at = now
                sent += 1
        await session.commit()
    logger.info(f"Weekly learning emails: {sent} sent, {skipped} skipped")
    return {"sent": sent, "skipped": skipped}


@celery_app.task(name="app.workers.tasks.weekly_learning.send_weekly_learning_emails")
def send_weekly_learning_emails() -> dict:
    return asyncio.run(_run())
