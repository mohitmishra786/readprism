from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.content import ContentItem
from app.models.digest import Digest, DigestFeedbackPrompt, DigestItem
from app.models.user import User
from app.schemas.content import ContentItemRead
from app.schemas.digest import DigestItemRead, DigestRead
from app.utils.logging import get_logger

router = APIRouter(prefix="/digest", tags=["digest"])
logger = get_logger(__name__)

RATE_LIMIT_FREE_MINUTES = 60


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
            select(Digest)
            .where(
                Digest.user_id == current_user.id,
                Digest.generated_at >= datetime.now(timezone.utc) - timedelta(minutes=RATE_LIMIT_FREE_MINUTES),
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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="answer is required")

    prompt.answer = answer
    prompt.answered = True
    await session.flush()
    return FeedbackPromptRead.model_validate(prompt)


async def _build_digest_read(digest: Digest, session: AsyncSession) -> DigestRead:
    items_result = await session.execute(
        select(DigestItem)
        .where(DigestItem.digest_id == digest.id)
        .order_by(DigestItem.position)
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
        item_reads.append(DigestItemRead(
            id=di.id,
            digest_id=di.digest_id,
            content_item_id=di.content_item_id,
            position=di.position,
            section=di.section,
            prs_score=di.prs_score,
            signal_breakdown=di.signal_breakdown or {},
            content=ContentItemRead.model_validate(content) if content else None,
        ))

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
