from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.content import ContentItem, UserContentInteraction
from app.models.digest import Digest, DigestFeedbackPrompt, DigestItem
from app.models.user import User
from app.schemas.content import ContentItemRead
from app.schemas.digest import DigestItemRead, DigestRead
from app.utils.logging import get_logger
from app.utils.signed_links import ACTIONS, verify_action
from app.utils.unsubscribe import verify_unsubscribe_token

router = APIRouter(prefix="/digest", tags=["digest"])
logger = get_logger(__name__)

RATE_LIMIT_FREE_MINUTES = 60


async def _apply_unsubscribe(uid: str, token: str, session: AsyncSession) -> bool:
    """Verify the signed token and switch the user to in-app-only (no email).
    Returns True if a user was updated."""
    try:
        user_uuid = uuid.UUID(uid)
    except (ValueError, TypeError):
        return False
    if not verify_unsubscribe_token(uid, token):
        return False
    result = await session.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None:
        return False
    user.digest_frequency = "in_app_only"
    await session.flush()
    # Log the parsed UUID (validated above), never the raw request string.
    logger.info(f"User {user_uuid} unsubscribed from digest emails via email link")
    return True


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_get(
    uid: str = Query(...),
    token: str = Query(...),
    session: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """One-click unsubscribe target for the digest email footer link."""
    ok = await _apply_unsubscribe(uid, token, session)
    if not ok:
        return HTMLResponse("<p>This unsubscribe link is invalid or expired.</p>", status_code=400)
    return HTMLResponse(
        "<p>You've been unsubscribed from ReadPrism digest emails. "
        "You can re-enable them anytime in your preferences.</p>"
    )


@router.post("/unsubscribe", status_code=status.HTTP_200_OK)
async def unsubscribe_post(
    uid: str = Query(...),
    token: str = Query(...),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """RFC 8058 List-Unsubscribe-Post=One-Click endpoint (mail-client POST)."""
    ok = await _apply_unsubscribe(uid, token, session)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")
    return {"status": "unsubscribed"}


async def _record_email_action(
    user: User, item_id: uuid.UUID, action: str, session: AsyncSession
) -> UserContentInteraction:
    """Upsert the interaction row for a one-click email action (UX-04)."""
    result = await session.execute(
        select(UserContentInteraction).where(
            UserContentInteraction.user_id == user.id,
            UserContentInteraction.content_item_id == item_id,
        )
    )
    interaction = result.scalar_one_or_none()
    if interaction is None:
        interaction = UserContentInteraction(user_id=user.id, content_item_id=item_id)
        session.add(interaction)

    if action == "open":
        if not interaction.opened_at:
            interaction.opened_at = datetime.now(UTC)
    elif action == "up":
        interaction.explicit_rating = 1
        interaction.opened_at = interaction.opened_at or datetime.now(UTC)
    elif action == "down":
        interaction.explicit_rating = -1
    elif action == "save":
        interaction.saved = True
        if interaction.saved_at is None:
            interaction.saved_at = datetime.now(UTC)

    await session.flush()
    return interaction


def _confirmation_page(
    action: str, user_id: uuid.UUID, item_id: uuid.UUID, exp: int, sig: str
) -> HTMLResponse:
    """A one-tap confirmation page for mutating email actions.

    Corporate mail scanners (Safe Links, Mimecast) prefetch every link in an
    email with plain GETs and no JS. Mutating actions therefore render this
    page on GET instead of writing state: a scanner sees inert HTML, a real
    browser auto-submits the form (and a no-JS user can press the button),
    which POSTs back to the same signed URL and records the action.

    Every interpolated value is a server-validated type (allowlisted action,
    parsed UUIDs, int expiry, HMAC-matched hex signature) and is additionally
    HTML-escaped at the sink (CodeQL py/reflective-xss).
    """
    import html

    labels = {"up": "👍 Useful", "down": "👎 Not for me", "save": "💾 Save"}
    label = html.escape(labels.get(action, "Confirm"))
    target = html.escape(
        f"/api/v1/digest/e/{action}/{item_id}?uid={user_id}&exp={exp}&sig={sig}", quote=True
    )
    return HTMLResponse(
        f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ReadPrism — {label}</title>
<style>
 body {{ font-family: system-ui, sans-serif; display: flex; min-height: 100vh;
        align-items: center; justify-content: center; background: #f8fafc; margin: 0; }}
 .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
         padding: 32px 40px; text-align: center; }}
 button {{ font-size: 16px; padding: 10px 24px; border-radius: 8px; border: 1px solid #1d4ed8;
          background: #1d4ed8; color: #fff; cursor: pointer; }}
</style></head>
<body><div class="card">
<p>Confirm your feedback for this article:</p>
<form method="post" action="{target}" id="confirm">
  <button type="submit">{label}</button>
</form>
</div>
<script>document.getElementById("confirm").submit();</script>
</body></html>"""
    )


MUTATING_ACTIONS = {"up", "down", "save"}


async def _verify_email_action(
    action: str,
    item_id: uuid.UUID,
    uid: str,
    exp: int,
    sig: str,
    session: AsyncSession,
) -> tuple[User, ContentItem]:
    """Shared validation for the GET and POST email-action handlers."""
    # Allowlist the path parameter before anything else: every later use of
    # `action` (branching, logging) is then structurally bounded (CodeQL
    # py/log-injection).
    if action not in ACTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown action")

    try:
        user_uuid = uuid.UUID(uid)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad uid")

    if not verify_action(uid, item_id, action, exp, sig):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired link"
        )

    user_result = await session.execute(select(User).where(User.id == user_uuid))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown user")

    content_result = await session.execute(select(ContentItem).where(ContentItem.id == item_id))
    content = content_result.scalar_one_or_none()
    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content item not found")
    return user, content


def _reader_redirect(content: ContentItem) -> RedirectResponse:
    # The redirect target is built from the operator-configured frontend URL
    # and the database row's canonical id — never from a raw request string
    # (CodeQL py/url-redirect).
    reader_url = f"{get_settings().frontend_url.rstrip('/')}/read/{content.id}"
    return RedirectResponse(url=reader_url, status_code=303)


# Constant map for logging: the value printed comes from this table, never
# from the request string (CodeQL py/log-injection).
_LOG_ACTIONS = {name: name for name in ACTIONS}


def _log_email_action(action: str, user_id: uuid.UUID, item_id: uuid.UUID) -> None:
    logger.info(
        "Email action %s recorded for user %s item %s",
        _LOG_ACTIONS[action],
        user_id,
        item_id,
    )


@router.get("/e/{action}/{item_id}")
async def email_action_link(
    action: str,
    item_id: uuid.UUID,
    uid: str = Query(...),
    exp: int = Query(...),
    sig: str = Query(...),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Signed one-click email actions: open / thumbs up / thumbs down / save.

    No login: the HMAC over (user, item, action, expiry) is the authority.

    GET is non-mutating for up/down/save (it renders a confirmation page) so
    mail-scanner prefetch cannot forge ratings or saves. 'open' is a passive
    click-through: it records opened_at and redirects to the in-app reader so
    depth/dwell telemetry can follow (UX-04).
    """
    user, content = await _verify_email_action(action, item_id, uid, exp, sig, session)

    if action in MUTATING_ACTIONS:
        return _confirmation_page(action, user.id, content.id, exp, sig)

    await _record_email_action(user, content.id, action, session)
    _log_email_action(action, user.id, content.id)
    return _reader_redirect(content)


@router.post("/e/{action}/{item_id}")
async def email_action_submit(
    action: str,
    item_id: uuid.UUID,
    uid: str = Query(...),
    exp: int = Query(...),
    sig: str = Query(...),
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Record a mutating email action (form POST from the confirmation page)."""
    if action not in MUTATING_ACTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown action")
    user, content = await _verify_email_action(action, item_id, uid, exp, sig, session)

    interaction = await _record_email_action(user, content.id, action, session)
    # Commit before dispatching so the worker's own session can see the row
    # (get_db commits only after the response is returned — the task could
    # otherwise run first and find nothing).
    await session.commit()
    from app.workers.tasks.update_interest_graph import update_interest_graph_for_interaction

    update_interest_graph_for_interaction.delay(str(interaction.id))
    _log_email_action(action, user.id, content.id)
    return _reader_redirect(content)


@router.get("/latest", response_model=DigestRead)
async def get_latest_digest(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DigestRead:
    result = await session.execute(
        select(Digest)
        .where(Digest.user_id == current_user.id)
        .order_by(Digest.generated_at.desc())
        .limit(1)
    )
    digest = result.scalar_one_or_none()
    if not digest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No digest found")

    return await _build_digest_read(digest, session)


@router.get("/history", response_model=list[DigestRead])
async def get_digest_history(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DigestRead]:
    result = await session.execute(
        select(Digest)
        .where(Digest.user_id == current_user.id)
        .order_by(Digest.generated_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    digests = list(result.scalars().all())
    return [await _build_digest_read(d, session) for d in digests]


@router.get("/emerging", response_model=list[dict])
async def get_emerging_topics(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Topics with a burst of distinct-source coverage in the last 72 h vs
    the trailing 28-day baseline (UX-10). Powers the "Emerging" card.

    Public items only; per topic: distinct sources in the recent window
    compared with the four trailing 7-day windows (z >= 2).
    """
    from datetime import timedelta

    from sqlalchemy import func

    from app.services.digest.emerging import detect_emerging

    now = datetime.now(UTC)

    def distinct_sources_per_topic(start, end):
        topic = func.jsonb_array_elements_text(ContentItem.topic_clusters).label("topic")
        return (
            select(topic, func.count(func.distinct(ContentItem.source_id)).label("n"))
            .select_from(ContentItem)
            .where(
                ContentItem.fetched_at >= start,
                ContentItem.fetched_at < end,
                ContentItem.source_id.isnot(None),
                ContentItem.owner_user_id.is_(None),
            )
            .group_by(topic)
        )

    recent_result = await session.execute(
        distinct_sources_per_topic(now - timedelta(hours=72), now)
    )
    recent = {row[0]: int(row[1]) for row in recent_result.all()}

    # Four trailing 7-day windows that END where the recent window begins —
    # overlapping the recent window would absorb the burst into the baseline
    # and mute the z-score.
    base = now - timedelta(hours=72)
    history: dict[str, list[float]] = {}
    for week in range(4):
        end = base - timedelta(days=week * 7)
        start = end - timedelta(days=7)
        rows = await session.execute(distinct_sources_per_topic(start, end))
        for row in rows.fetchall():
            history.setdefault(str(row[0]), []).append(float(cast(int, row[1])))
    # Oldest-first, one slot per 7-day window even when a week had none.
    for topic in history:
        while len(history[topic]) < 4:
            history[topic].insert(0, 0.0)

    found = detect_emerging(recent, history)
    return [
        {
            "topic": e.topic,
            "recent_sources": e.recent_sources,
            "baseline_mean": round(e.baseline_mean, 2),
            "z": round(min(e.z, 99.0), 2),
        }
        for e in found[:5]
    ]


@router.post("/generate", response_model=dict)
async def generate_digest(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Rate limit: free tier max once per hour
    if current_user.tier == "free":
        recent = await session.execute(
            select(Digest).where(
                Digest.user_id == current_user.id,
                Digest.generated_at
                >= datetime.now(UTC) - timedelta(minutes=RATE_LIMIT_FREE_MINUTES),
            )
        )
        if recent.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Free tier: digest generation limited to once per hour",
            )

    from app.workers.tasks.build_digest import build_digest_for_user

    build_digest_for_user.delay(str(current_user.id))
    return {"status": "queued", "message": "Digest generation started"}


@router.get("/{digest_id}", response_model=DigestRead)
async def get_digest(
    digest_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DigestRead:
    result = await session.execute(
        select(Digest).where(Digest.id == digest_id, Digest.user_id == current_user.id)
    )
    digest = result.scalar_one_or_none()
    if not digest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Digest not found")
    return await _build_digest_read(digest, session)


class FeedbackPromptRead(BaseModel):
    id: uuid.UUID
    digest_id: uuid.UUID
    content_item_id: uuid.UUID | None
    prompt_text: str
    prompt_type: str
    answered: bool
    dismissed: bool
    answer: str | None

    model_config = {"from_attributes": True}


@router.get("/{digest_id}/prompts", response_model=list[FeedbackPromptRead])
async def get_digest_prompts(
    digest_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[FeedbackPromptRead]:
    """Return feedback prompts for an early-user digest."""
    # Verify ownership
    digest_result = await session.execute(
        select(Digest).where(Digest.id == digest_id, Digest.user_id == current_user.id)
    )
    if not digest_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Digest not found")

    prompts_result = await session.execute(
        select(DigestFeedbackPrompt).where(DigestFeedbackPrompt.digest_id == digest_id)
    )
    return [FeedbackPromptRead.model_validate(p) for p in prompts_result.scalars().all()]


@router.post("/{digest_id}/prompts/{prompt_id}/answer", response_model=FeedbackPromptRead)
async def answer_digest_prompt(
    digest_id: uuid.UUID,
    prompt_id: uuid.UUID,
    body: dict,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FeedbackPromptRead:
    """Record a user's answer to a feedback prompt."""
    digest_result = await session.execute(
        select(Digest).where(Digest.id == digest_id, Digest.user_id == current_user.id)
    )
    if not digest_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Digest not found")

    prompt_result = await session.execute(
        select(DigestFeedbackPrompt).where(
            DigestFeedbackPrompt.id == prompt_id,
            DigestFeedbackPrompt.digest_id == digest_id,
        )
    )
    prompt = prompt_result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")

    answer = str(body.get("answer", "")).strip()
    if not answer:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="answer is required"
        )

    prompt.answer = answer
    prompt.answered = True
    await session.flush()
    return FeedbackPromptRead.model_validate(prompt)


@router.post("/{digest_id}/prompts/{prompt_id}/dismiss", response_model=FeedbackPromptRead)
async def dismiss_digest_prompt(
    digest_id: uuid.UUID,
    prompt_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FeedbackPromptRead:
    """Dismiss an early-feedback prompt without answering (UX-07)."""
    digest_result = await session.execute(
        select(Digest).where(Digest.id == digest_id, Digest.user_id == current_user.id)
    )
    if not digest_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Digest not found")

    prompt_result = await session.execute(
        select(DigestFeedbackPrompt).where(
            DigestFeedbackPrompt.id == prompt_id,
            DigestFeedbackPrompt.digest_id == digest_id,
        )
    )
    prompt = prompt_result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")

    prompt.dismissed = True
    await session.flush()
    return FeedbackPromptRead.model_validate(prompt)


async def _build_digest_read(digest: Digest, session: AsyncSession) -> DigestRead:
    items_result = await session.execute(
        select(DigestItem).where(DigestItem.digest_id == digest.id).order_by(DigestItem.position)
    )
    digest_items = list(items_result.scalars().all())

    content_ids = [di.content_item_id for di in digest_items]
    content_map: dict = {}
    if content_ids:
        content_result = await session.execute(
            select(ContentItem).where(ContentItem.id.in_(content_ids))
        )
        content_map = {c.id: c for c in content_result.scalars().all()}

    item_reads = []
    for di in digest_items:
        content = content_map.get(di.content_item_id)
        item_reads.append(
            DigestItemRead(
                id=di.id,
                digest_id=di.digest_id,
                content_item_id=di.content_item_id,
                position=di.position,
                section=di.section,
                prs_score=di.prs_score,
                signal_breakdown=di.signal_breakdown or {},
                content=ContentItemRead.model_validate(content) if content else None,
            )
        )

    return DigestRead(
        id=digest.id,
        user_id=digest.user_id,
        generated_at=digest.generated_at,
        delivered_at=digest.delivered_at,
        delivery_method=digest.delivery_method,
        section_counts=digest.section_counts or {},
        opened=digest.opened,
        total_items=digest.total_items,
        items=item_reads,
        created_at=digest.created_at,
    )
