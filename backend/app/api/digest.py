from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
) -> None:
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

    await session.flush()

    if action in {"up", "down", "save"} and interaction.id is not None:
        from app.workers.tasks.update_interest_graph import update_interest_graph_for_interaction

        update_interest_graph_for_interaction.delay(str(interaction.id))


@router.get("/e/{action}/{item_id}")
async def email_action_link(
    action: str,
    item_id: uuid.UUID,
    uid: str = Query(...),
    exp: int = Query(...),
    sig: str = Query(...),
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Signed one-click email actions: open / thumbs up / thumbs down / save.

    No login: the HMAC over (user, item, action, expiry) is the authority.
    Records the feedback, then redirects into the in-app reader so the normal
    telemetry (depth, dwell) can follow (UX-04).
    """
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

    await _record_email_action(user, content.id, action, session)
    logger.info(f"Email action {action} recorded for user {user_uuid} item {content.id}")

    # The redirect target is built from the operator-configured frontend URL
    # and the database row's canonical id — never from a raw request string
    # (CodeQL py/url-redirect).
    reader_url = f"{get_settings().frontend_url.rstrip('/')}/read/{content.id}"
    return RedirectResponse(url=reader_url, status_code=303)


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
