from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.schemas.content import ContentItemRead, FeedItem
from app.utils.logging import get_logger

router = APIRouter(prefix="/content", tags=["content"])
logger = get_logger(__name__)


@router.get("/feed", response_model=list[FeedItem])
async def get_feed(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    section: str | None = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[FeedItem]:
    offset = (page - 1) * limit

    # Get interactions with PRS scores for this user
    query = (
        select(ContentItem, UserContentInteraction)
        .join(
            UserContentInteraction,
            (UserContentInteraction.content_item_id == ContentItem.id)
            & (UserContentInteraction.user_id == current_user.id),
            isouter=True,
        )
        .order_by(UserContentInteraction.prs_score.desc().nullslast())
        .offset(offset)
        .limit(limit)
    )

    result = await session.execute(query)
    rows = result.fetchall()

    feed_items = []
    for content_item, interaction in rows:
        feed_items.append(FeedItem(
            content=ContentItemRead.model_validate(content_item),
            prs_score=interaction.prs_score if interaction else None,
            signal_breakdown={},
        ))

    return feed_items


@router.get("/history", response_model=list[FeedItem])
async def get_reading_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[FeedItem]:
    """Return articles the user has actually opened, ordered by most recently read."""
    offset = (page - 1) * limit

    result = await session.execute(
        select(ContentItem, UserContentInteraction)
        .join(
            UserContentInteraction,
            (UserContentInteraction.content_item_id == ContentItem.id)
            & (UserContentInteraction.user_id == current_user.id),
        )
        .where(UserContentInteraction.opened_at.is_not(None))
        .order_by(UserContentInteraction.opened_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = result.fetchall()

    return [
        FeedItem(
            content=ContentItemRead.model_validate(content_item),
            prs_score=interaction.prs_score,
            signal_breakdown={},
        )
        for content_item, interaction in rows
    ]


@router.get("/{content_id}", response_model=ContentItemRead)
async def get_content(
    content_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContentItemRead:
    result = await session.execute(select(ContentItem).where(ContentItem.id == content_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
    return ContentItemRead.model_validate(item)
