from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.schemas.content import ContentItemFullRead, ContentItemRead, FeedItem
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

    from sqlalchemy import or_

    from app.services.feed_identity import (
        equivalent_source_ids,
        from_user_feeds,
        user_feed_ids,
        visible_item_filter,
    )

    # Only this user's world (#167): items from feeds they follow, their own
    # private items, and items they interacted with. The outer join used to
    # list every row in the instance, including other users' private
    # newsletters and saves.
    source_ids = await equivalent_source_ids(session, current_user.id)
    feed_ids = await user_feed_ids(session, current_user.id)
    from app.services.takedown import not_blocked_filter

    in_scope = or_(
        from_user_feeds(source_ids, feed_ids),
        ContentItem.owner_user_id == current_user.id,
        UserContentInteraction.id.isnot(None),
    )
    query = (
        select(ContentItem, UserContentInteraction)
        .join(
            UserContentInteraction,
            (UserContentInteraction.content_item_id == ContentItem.id)
            & (UserContentInteraction.user_id == current_user.id),
            isouter=True,
        )
        .where(in_scope, visible_item_filter(current_user.id), not_blocked_filter())
        .order_by(
            UserContentInteraction.prs_score.desc().nullslast(),
            ContentItem.fetched_at.desc(),
        )
        .offset(offset)
        .limit(limit)
    )

    result = await session.execute(query)
    rows = result.fetchall()

    from app.models.digest import DigestImpression
    from app.services.ranking.learning import RANKER_VERSION

    feed_items = []
    for index, (content_item, interaction) in enumerate(rows):
        feed_items.append(
            FeedItem(
                content=ContentItemRead.model_validate(content_item),
                prs_score=interaction.prs_score if interaction else None,
                signal_breakdown={},
            )
        )
        session.add(
            DigestImpression(
                user_id=current_user.id,
                content_item_id=content_item.id,
                section=section or "feed",
                position=offset + index,
                score=float(interaction.prs_score)
                if interaction and interaction.prs_score is not None
                else 0.0,
                features_json={},
                weights_version=RANKER_VERSION,
            )
        )

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


@router.get("/saved", response_model=list[FeedItem])
async def get_saved_queue(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[FeedItem]:
    """The user's saved queue, newest save first (UX-12).

    Items saved and then fully read leave the queue; unread saves stay until
    read (a 14-day unopened save becomes a slight negative label).
    """
    offset = (page - 1) * limit

    result = await session.execute(
        select(ContentItem, UserContentInteraction)
        .join(
            UserContentInteraction,
            (UserContentInteraction.content_item_id == ContentItem.id)
            & (UserContentInteraction.user_id == current_user.id),
        )
        .where(
            UserContentInteraction.saved.is_(True), UserContentInteraction.saved_read_at.is_(None)
        )
        .order_by(UserContentInteraction.saved_at.desc().nullslast())
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


@router.get("/{content_id}", response_model=ContentItemFullRead)
async def get_content(
    content_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContentItemFullRead:
    result = await session.execute(select(ContentItem).where(ContentItem.id == content_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
    from app.services.takedown import is_url_blocked

    if await is_url_blocked(session, item.url):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
    # Private content (e.g. forwarded newsletters) is readable only by its owner.
    # Return 404 (not 403) so non-owners can't even confirm the item exists
    # (audit 06-6).
    if item.owner_user_id is not None and item.owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
    await _queue_llm_summary(item, current_user, session)
    from app.services.display_policy import may_display_full_text

    read = ContentItemFullRead.model_validate(item)
    if read.full_text and not may_display_full_text(item, current_user.id):
        read.full_text = None
        read.full_text_withheld = True
    return read


async def _queue_llm_summary(item: ContentItem, user: User, session: AsyncSession) -> None:
    """Someone is reading it: get the model summary in the background (#147).

    On the reader's own key if they have one (#255); otherwise it counts
    against their plan's daily AI summaries (#172).
    """
    from app.config import get_settings
    from app.services import entitlements
    from app.services.llm import user_keys
    from app.services.summarization.lazy import needs_llm_summary
    from app.utils.cache import cache_set_nx

    if not needs_llm_summary(item):
        return
    own_key = user_keys.available() and await user_keys.get(session, user.id) is not None
    if not own_key and not get_settings().llm_configured:
        return
    if not own_key and await entitlements.remaining_today(user, entitlements.LLM_SUMMARIES) == 0:
        return
    if await cache_set_nx(f"llm-summary-queued:{item.id}", 1, ttl_seconds=3600):
        from app.workers.tasks.compute_embeddings import summarize_item_with_llm

        if own_key:
            summarize_item_with_llm.delay(str(item.id), str(user.id))
        else:
            await entitlements.record_use(user, entitlements.LLM_SUMMARIES)
            summarize_item_with_llm.delay(str(item.id))
