"""Extension endpoints (EC-02): save & rate the current page.

`origin=extension` items are PRIVATE (owner_user_id set) like forwarded
newsletters: a saved page is user-specific. Saving + rating is a strong
explicit signal for the ranker.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.utils.logging import get_logger

router = APIRouter(prefix="/extension", tags=["extension"])
logger = get_logger(__name__)


class ExtensionSave(BaseModel):
    url: str = Field(..., min_length=8, max_length=2000)
    title: str = Field(..., min_length=1, max_length=500)
    rating: int | None = None  # 1 / -1 / None (save only)


@router.post("/save", status_code=status.HTTP_201_CREATED)
async def save_and_rate(
    body: ExtensionSave,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if body.rating is not None and body.rating not in (1, -1):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="rating must be 1 or -1"
        )

    from datetime import UTC, datetime

    result = await session.execute(select(ContentItem).where(ContentItem.url == body.url))
    item = result.scalar_one_or_none()
    if (
        item is not None
        and item.owner_user_id is not None
        and item.owner_user_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="URL already saved by another user"
        )
    if item is None:
        item = ContentItem(
            url=body.url,
            title=body.title,
            origin="extension",
            owner_user_id=current_user.id,  # private: never another user's discovery pool
            fetched_at=datetime.now(UTC),
            rankable=True,
        )
        session.add(item)
        await session.flush()
    elif item.owner_user_id is None:
        # Public item already ingested from a feed: keep it public, just rate it.
        pass

    ix_result = await session.execute(
        select(UserContentInteraction).where(
            UserContentInteraction.user_id == current_user.id,
            UserContentInteraction.content_item_id == item.id,
        )
    )
    interaction = ix_result.scalar_one_or_none()
    if interaction is None:
        interaction = UserContentInteraction(
            user_id=current_user.id,
            content_item_id=item.id,
            saved=True,
            explicit_rating=body.rating,
        )
        session.add(interaction)
    else:
        interaction.saved = True
        if body.rating is not None:
            interaction.explicit_rating = body.rating

    await session.flush()
    logger.info(f"Extension save for user {current_user.id} item {item.id}")
    return {"status": "ok", "content_item_id": str(item.id)}
