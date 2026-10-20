"""Trial lifecycle emails on hosted (#235).

Three emails, one each per account, by where the trial stands:

1. started: what the trial includes and when it ends;
2. ending soon: TRIAL_ENDING_NOTICE_DAYS before the end;
3. ended: the account is on the Free limits; nothing is deleted and the
   export keeps working.

Accounts that bought a plan get no "ending" or "ended" email. A missed stage
is skipped, never sent together with the next one. Every email goes through
may_email and carries List-Unsubscribe.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.utils.logging import get_logger
from app.workers.celery_app import celery_app
from app.workers.tasks.reengagement import _button, _shell

logger = get_logger(__name__)

STARTED, ENDING, ENDED = 1, 2, 3


def due_stage(
    *, trial_ends_at: datetime, current_stage: int, paid: bool, now: datetime
) -> int | None:
    """The stage to send now, or None. Pure; tested per transition."""
    notice = timedelta(days=get_settings().trial_ending_notice_days)
    if now >= trial_ends_at:
        reached = ENDED
    elif now >= trial_ends_at - notice:
        reached = ENDING
    else:
        reached = STARTED
    if reached <= current_stage:
        return None
    if paid and reached != STARTED:
        return None
    return reached


def _day(moment: datetime) -> str:
    return f"{moment:%B} {moment.day}"


def render(stage: int, *, frontend: str, unsubscribe: str, ends: datetime) -> tuple[str, str, str]:
    """(subject, html, text) for a stage."""
    from app.services.entitlements import plan_quotas

    plans = f"{frontend}/preferences#plan"
    export = f"{frontend}/preferences"
    if stage == STARTED:
        subject = f"Your ReadPrism trial runs until {_day(ends)}"
        lines = [
            f"Your free trial is on until {_day(ends)}. It includes everything the Reader plan does, "
            "and no card is needed.",
            "Add the feeds and newsletters you read; your digest learns from what you open and rate.",
        ]
        buttons = [(f"{frontend}/digest", "Open ReadPrism")]
    elif stage == ENDING:
        subject = f"Your ReadPrism trial ends on {_day(ends)}"
        free = plan_quotas("free")
        lines = [
            f"Your trial ends on {_day(ends)}. To keep your current limits, choose a plan before then.",
            "If you don't, nothing is deleted: your account moves to the Free limits "
            f"({free['sources']} feeds, {free['llm_summaries_per_day']} AI summaries a day), "
            "and you can export everything at any time.",
        ]
        buttons = [(plans, "See plans")]
    else:
        subject = "Your ReadPrism trial has ended"
        lines = [
            "Your trial has ended and your account is now on the Free limits. Your sources, saved "
            "articles and ratings are all kept.",
            "You can pick a plan whenever you like, or download a full export of your data.",
        ]
        buttons = [(plans, "See plans"), (export, "Export my data")]
    body = "".join(f"<p>{line}</p>" for line in lines) + "".join(
        _button(u, label) for u, label in buttons
    )
    text = "\n\n".join(lines) + "\n\n" + "\n".join(f"{label}: {u}" for u, label in buttons)
    return subject, _shell(body, unsubscribe), f"{text}\n\nStop digest emails: {unsubscribe}"


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


async def _run(now: datetime | None = None) -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.billing import PAID_TIERS, effective_plan
    from app.services.email_verification import may_email
    from app.utils.email import send_email
    from app.utils.unsubscribe import unsubscribe_url

    settings = get_settings()
    if settings.deployment_mode != "hosted":
        return {"sent": 0}
    now = now or datetime.now(UTC)
    frontend = settings.frontend_url.rstrip("/")
    sent = {STARTED: 0, ENDING: 0, ENDED: 0}
    async with AsyncSessionLocal() as session:
        users = (
            await session.execute(
                select(User).where(User.trial_ends_at.is_not(None), User.trial_email_stage < ENDED)
            )
        ).scalars()
        for user in users:
            ends = _aware(user.trial_ends_at)  # type: ignore[arg-type]
            paid = effective_plan(user, now=now) in PAID_TIERS
            if paid and now >= ends:
                user.trial_email_stage = ENDED  # bought a plan: nothing left to say
                continue
            stage = due_stage(
                trial_ends_at=ends, current_stage=user.trial_email_stage or 0, paid=paid, now=now
            )
            if stage is None or not may_email(user):
                continue
            unsubscribe = unsubscribe_url(user.id)
            subject, html_body, text_body = render(
                stage, frontend=frontend, unsubscribe=unsubscribe, ends=ends
            )
            ok = await send_email(
                to=user.email,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                extra_headers={
                    "List-Unsubscribe": f"<{unsubscribe}>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                },
            )
            if ok:
                user.trial_email_stage = stage
                sent[stage] += 1
        await session.commit()
    logger.info(f"Trial emails sent: {sent}")
    return {"sent": sum(sent.values()), "by_stage": sent}


@celery_app.task(name="app.workers.tasks.trial_emails.send_trial_emails")
def send_trial_emails() -> dict:
    return asyncio.run(_run())
