from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.schemas.content import UserContentInteractionCreate, UserContentInteractionRead
from app.schemas.ranking import InterestAdjustment
from app.services.interest_graph.graph import InterestGraphManager
from app.utils.logging import get_logger

router = APIRouter(prefix="/feedback", tags=["feedback"])
logger = get_logger(__name__)
graph_manager = InterestGraphManager()


@router.post("/interaction", response_model=UserContentInteractionRead)
async def record_interaction(
    body: UserContentInteractionCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserContentInteractionRead:
    # Verify content exists
    content_result = await session.execute(
        select(ContentItem).where(ContentItem.id == body.content_item_id)
    )
    content = content_result.scalar_one_or_none()
    if not content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content item not found")

    # Upsert interaction
    existing_result = await session.execute(
        select(UserContentInteraction).where(
            UserContentInteraction.user_id == current_user.id,
            UserContentInteraction.content_item_id == body.content_item_id,
        )
    )
    interaction = existing_result.scalar_one_or_none()

    if interaction:
        if body.read_completion_pct is not None:
            interaction.read_completion_pct = body.read_completion_pct
        if body.time_on_page_seconds is not None:
            interaction.time_on_page_seconds = body.time_on_page_seconds
        if body.explicit_rating is not None:
            interaction.explicit_rating = body.explicit_rating
        if body.explicit_rating_reason is not None:
            interaction.explicit_rating_reason = body.explicit_rating_reason
        if body.saved:
            interaction.saved = True
        if body.skipped:
            interaction.skipped = True
        if body.read_completion_pct and not interaction.opened_at:
            interaction.opened_at = datetime.now(timezone.utc)
        # Set saved_read_at when a previously saved article is fully read
        if (
            interaction.saved
            and body.read_completion_pct is not None
            and body.read_completion_pct >= 0.9
            and interaction.saved_read_at is None
        ):
            interaction.saved_read_at = datetime.now(timezone.utc)
        # Update re_read_count when already fully read and being read again
        if (
            body.read_completion_pct is not None
            and body.read_completion_pct >= 0.85
            and interaction.read_completion_pct is not None
            and interaction.read_completion_pct >= 0.85
        ):
            interaction.re_read_count = (interaction.re_read_count or 0) + 1
    else:
        interaction = UserContentInteraction(
            user_id=current_user.id,
            content_item_id=body.content_item_id,
            read_completion_pct=body.read_completion_pct,
            time_on_page_seconds=body.time_on_page_seconds,
            explicit_rating=body.explicit_rating,
            explicit_rating_reason=body.explicit_rating_reason,
            saved=body.saved,
            skipped=body.skipped,
            opened_at=datetime.now(timezone.utc) if body.read_completion_pct else None,
        )
        session.add(interaction)

    await session.flush()

    # Enqueue interest graph update
    from app.workers.tasks.update_interest_graph import update_interest_graph_for_interaction
    update_interest_graph_for_interaction.delay(str(interaction.id))

    return UserContentInteractionRead.model_validate(interaction)


@router.get("/interaction/{content_id}", response_model=UserContentInteractionRead | None)
async def get_interaction(
    content_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserContentInteractionRead | None:
    """Return the current user's interaction record for a content item, if any."""
    result = await session.execute(
        select(UserContentInteraction).where(
            UserContentInteraction.user_id == current_user.id,
            UserContentInteraction.content_item_id == content_id,
        )
    )
    interaction = result.scalar_one_or_none()
    if interaction is None:
        return None
    return UserContentInteractionRead.model_validate(interaction)


@router.post("/adjust-interests")
async def adjust_interests(
    body: InterestAdjustment,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.models.interest_graph import InterestNode

    result = await session.execute(
        select(InterestNode).where(
            InterestNode.user_id == current_user.id,
            InterestNode.topic_label == body.topic,
        )
    )
    node = result.scalar_one_or_none()

    if body.action == "boost":
        if node:
            node.weight = min(1.0, node.weight + 0.3)
        else:
            from app.utils.embeddings import get_embedding_service
            emb = await get_embedding_service().encode_single(body.topic)
            node = InterestNode(
                user_id=current_user.id,
                topic_label=body.topic,
                topic_embedding=emb,
                weight=0.7,
            )
            session.add(node)
    elif body.action == "suppress" and node:
        node.weight = max(0.0, node.weight - 0.3)
        if body.duration_days is not None and body.duration_days > 0:
            node.suppressed_until = datetime.now(timezone.utc) + timedelta(days=body.duration_days)
    elif body.action == "remove" and node:
        node.weight = 0.01

    await session.flush()

    from app.utils.cache import cache_delete
    await cache_delete(f"interest_vec:{current_user.id}")

    return {"status": "ok", "topic": body.topic, "action": body.action}
