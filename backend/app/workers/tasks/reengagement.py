"""Gentle win-back for readers who stopped opening their digest (#238).

One email per stage, by days since the last opened digest (or since sign-up
for someone who never opened one), never more than one every
REENGAGEMENT_MIN_GAP_DAYS:

1. day 3: a lighter digest, just the top 3 items;
2. day 10: "pause, or switch to a weekly digest?" with one-click links;
3. day 30: a last note: we'll stop nudging, here's how to export your data.

Opening a digest resets the reader to stage 0. No guilt copy. Every email
goes through may_email and carries List-Unsubscribe.
"""

from __future__ import annotations

import asyncio
import html
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.utils.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

LIGHT, ASK, FINAL = 1, 2, 3


def stage_days() -> list[int]:
    days = [int(x) for x in get_settings().reengagement_stage_days.split(",") if x.strip()]
    return sorted(days)[:3]


def due_stage(
    *, days_inactive: float, current_stage: int, last_sent: datetime | None, now: datetime
) -> int | None:
    """The stage to send now, or None. Pure; tested per transition."""
    reached = sum(1 for d in stage_days() if days_inactive >= d)
    if reached <= current_stage:
        return None
    gap = timedelta(days=get_settings().reengagement_min_gap_days)
    if last_sent is not None and now - last_sent < gap:
        return None
    return reached  # skip stages that were missed; never send two at once


def _shell(body: str, unsubscribe: str) -> str:
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:520px;margin:0 auto;color:#1c1917">'
        f"{body}"
        f'<p style="font-size:12px;color:#78716c;margin-top:24px">'
        f'<a href="{html.escape(unsubscribe, quote=True)}" style="color:#78716c">Stop digest emails</a></p></div>'
    )


def _button(href: str, label: str) -> str:
    return (
        f'<a href="{html.escape(href, quote=True)}" style="display:inline-block;background:#1c1917;color:#fff;'
        f'padding:9px 16px;border-radius:16px;text-decoration:none;margin:4px 6px 4px 0">{html.escape(label)}</a>'
    )


def render(
    stage: int, *, frontend: str, unsubscribe: str, top: list[tuple[str, str]], weekly_url: str
) -> tuple[str, str, str]:
    """(subject, html, text) for a stage. `top` is [(title, open_url)]."""
    if stage == LIGHT:
        subject = "Three picks from your sources"
        if top:
            items = "".join(
                f'<li style="margin:6px 0"><a href="{html.escape(u, quote=True)}">{html.escape(t)}</a></li>'
                for t, u in top
            )
            text_items = "\n".join(f"- {t}: {u}" for t, u in top)
        else:
            items, text_items = "", ""
        body = (
            "<p>A shorter one today: the three items ReadPrism ranked highest for you.</p>"
            f"<ol>{items}</ol>" + _button(f"{frontend}/digest", "Open the full digest")
        )
        text = f"A shorter one today: the three items ReadPrism ranked highest for you.\n\n{text_items}\n\nFull digest: {frontend}/digest"
    elif stage == ASK:
        subject = "Would a weekly digest suit you better?"
        body = (
            "<p>Daily might be too much right now, and that's fine. You can switch to one digest a week, "
            "or pause digest emails and read in the app when you like.</p>"
            + _button(weekly_url, "Switch to weekly")
            + _button(unsubscribe, "Pause digest emails")
            + _button(f"{frontend}/digest", "Keep daily")
        )
        text = (
            "Daily might be too much right now, and that's fine.\n\n"
            f"Switch to weekly: {weekly_url}\nPause digest emails: {unsubscribe}\nKeep daily: {frontend}/digest"
        )
    else:
        subject = "We'll stop nudging you"
        body = (
            "<p>This is the last reminder ReadPrism will send. Your sources keep being ranked, and everything "
            "is here whenever you come back.</p>"
            "<p>If you'd rather take your reading elsewhere, you can download all of it (sources, saved "
            "articles, ratings) as a portable export.</p>"
            + _button(f"{frontend}/preferences", "Export my data")
            + _button(f"{frontend}/digest", "Open ReadPrism")
        )
        text = (
            "This is the last reminder ReadPrism will send. Everything is here whenever you come back.\n\n"
            f"Export your data: {frontend}/preferences\nOpen ReadPrism: {frontend}/digest"
        )
    return subject, _shell(body, unsubscribe), f"{text}\n\nStop digest emails: {unsubscribe}"


async def _top_three(session, user_id) -> list[tuple]:
    from sqlalchemy import select

    from app.models.content import ContentItem
    from app.models.digest import Digest, DigestItem
    from app.utils.signed_links import action_url

    latest = (
        await session.execute(
            select(Digest.id)
            .where(Digest.user_id == user_id)
            .order_by(Digest.generated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is None:
        return []
    rows = (
        await session.execute(
            select(ContentItem.id, ContentItem.title)
            .join(DigestItem, DigestItem.content_item_id == ContentItem.id)
            .where(DigestItem.digest_id == latest)
            .order_by(DigestItem.position)
            .limit(3)
        )
    ).all()
    return [(title or "Untitled", action_url(user_id, cid, "open")) for cid, title in rows]


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


async def _run(now: datetime | None = None) -> dict:
    from sqlalchemy import func, select

    from app.database import AsyncSessionLocal
    from app.models.digest import Digest
    from app.models.user import User
    from app.services.email_verification import may_email
    from app.utils.email import send_email
    from app.utils.signed_links import user_action_url
    from app.utils.unsubscribe import unsubscribe_url

    settings = get_settings()
    now = now or datetime.now(UTC)
    frontend = settings.frontend_url.rstrip("/")
    sent = {LIGHT: 0, ASK: 0, FINAL: 0}
    async with AsyncSessionLocal() as session:
        users = list(
            (
                await session.execute(
                    select(User).where(
                        User.onboarding_complete.is_(True), User.digest_frequency != "in_app_only"
                    )
                )
            ).scalars()
        )
        opened_rows = (
            await session.execute(
                select(Digest.user_id, func.max(Digest.generated_at))
                .where(Digest.opened.is_(True))
                .group_by(Digest.user_id)
            )
        ).all()
        opened: dict = {row[0]: row[1] for row in opened_rows}
        for user in users:
            last_open = _aware(opened.get(user.id)) or _aware(user.created_at) or now
            last_sent = _aware(user.reengagement_sent_at)
            # Came back since the last nudge: start over.
            if user.reengagement_stage and last_sent is not None and last_open > last_sent:
                user.reengagement_stage = 0
            stage = due_stage(
                days_inactive=(now - last_open).total_seconds() / 86400,
                current_stage=user.reengagement_stage or 0,
                last_sent=last_sent,
                now=now,
            )
            if stage is None or not may_email(user):
                continue
            unsubscribe = unsubscribe_url(user.id)
            subject, html_body, text_body = render(
                stage,
                frontend=frontend,
                unsubscribe=unsubscribe,
                top=await _top_three(session, user.id) if stage == LIGHT else [],
                weekly_url=user_action_url(user.id, "weekly"),
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
                user.reengagement_stage = stage
                user.reengagement_sent_at = now
                if stage == FINAL and settings.reengagement_pause_digest_at_final:
                    user.digest_frequency = "in_app_only"
                sent[stage] += 1
        await session.commit()
    logger.info(f"Win-back emails sent: {sent}")
    return {"sent": sum(sent.values()), "by_stage": sent}


@celery_app.task(name="app.workers.tasks.reengagement.send_reengagement_emails")
def send_reengagement_emails() -> dict:
    return asyncio.run(_run())
