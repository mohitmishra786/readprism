from __future__ import annotations

import uuid
from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.creator import Creator
from app.models.user import User
from app.schemas.creator import CreatorCreate, CreatorRead, CreatorResolutionResult, CreatorUpdate
from app.services.creator.resolver import PLATFORM_CAPABILITIES, resolve_creator
from app.services.entitlements import enforce_creator_limit
from app.utils.logging import get_logger

router = APIRouter(prefix="/creators", tags=["creators"])
logger = get_logger(__name__)


@router.get("/platform-capabilities")
async def get_platform_capabilities(
    current_user: User = Depends(get_current_user),
) -> dict[str, dict[str, str]]:
    """Return the platform tracking-tier map so the frontend can render honest
    badges (fully tracked / best-effort / unsupported) on creator forms."""
    return PLATFORM_CAPABILITIES


@router.post("", response_model=CreatorResolutionResult, status_code=status.HTTP_201_CREATED)
async def add_creator(
    body: CreatorCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CreatorResolutionResult:
    # Enforce the free-tier creator limit (audit 13-1/13-5).
    count = (
        await session.execute(
            select(func.count()).select_from(Creator).where(Creator.user_id == current_user.id)
        )
    ).scalar() or 0
    enforce_creator_limit(current_user, count)

    result = await resolve_creator(body.name_or_url, current_user.id, session)
    if body.priority != "normal":
        result.creator.priority = body.priority
        await session.flush()

    # Eager-load the platforms relationship before serialization, otherwise
    # Pydantic's lazy attribute access triggers IO outside an awaited context
    # (MissingGreenlet error). The other endpoints do the same via refresh().
    await session.refresh(result.creator, ["platforms"])
    creator_read = CreatorRead.model_validate(result.creator)
    return CreatorResolutionResult(
        creator=creator_read,
        platforms_discovered=result.platforms_discovered,
        warning=result.warning,
    )


@router.get("", response_model=list[CreatorRead])
async def list_creators(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CreatorRead]:
    result = await session.execute(select(Creator).where(Creator.user_id == current_user.id))
    creators = list(result.scalars().all())
    out = []
    for c in creators:
        await session.refresh(c, ["platforms"])
        out.append(CreatorRead.model_validate(c))
    return out


@router.get("/{creator_id}", response_model=CreatorRead)
async def get_creator(
    creator_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CreatorRead:
    result = await session.execute(
        select(Creator).where(Creator.id == creator_id, Creator.user_id == current_user.id)
    )
    creator = result.scalar_one_or_none()
    if not creator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")
    await session.refresh(creator, ["platforms"])
    return CreatorRead.model_validate(creator)


@router.get("/{creator_id}/summary")
async def get_creator_summary(
    creator_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await session.execute(
        select(Creator).where(Creator.id == creator_id, Creator.user_id == current_user.id)
    )
    creator = result.scalar_one_or_none()
    if not creator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")

    from datetime import datetime, timedelta

    from app.models.content import ContentItem
    from app.models.creator import CreatorPlatform
    from app.services.summarization.groq_client import GroqSummarizer, SummarizationResult

    cutoff = datetime.now(UTC) - timedelta(days=7)
    platforms_result = await session.execute(
        select(CreatorPlatform.id).where(CreatorPlatform.creator_id == creator_id)
    )
    platform_ids = [row[0] for row in platforms_result.fetchall()]

    content_result = await session.execute(
        select(ContentItem)
        .where(
            ContentItem.creator_platform_id.in_(platform_ids),
            ContentItem.fetched_at >= cutoff,
        )
        .limit(5)
    )
    recent_items = list(content_result.scalars().all())

    if not recent_items:
        return {"summary": f"No recent content from {creator.display_name} in the past week."}

    groq = GroqSummarizer()
    summaries = [
        SummarizationResult(
            headline=item.summary_headline or item.title,
            brief=item.summary_brief or "",
            detailed="",
            depth_score=0.5,
            is_original_reporting=False,
            has_citations=False,
            topic_clusters=[],
            reading_time_minutes=5,
        )
        for item in recent_items
        if item.summary_brief
    ]
    if not summaries:
        return {"summary": f"{creator.display_name} published {len(recent_items)} items this week."}

    summary_text = await groq.synthesize_topic(summaries, f"{creator.display_name}'s recent work")
    return {"summary": summary_text, "item_count": len(recent_items)}


@router.put("/{creator_id}", response_model=CreatorRead)
async def update_creator(
    creator_id: uuid.UUID,
    body: CreatorUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CreatorRead:
    result = await session.execute(
        select(Creator).where(Creator.id == creator_id, Creator.user_id == current_user.id)
    )
    creator = result.scalar_one_or_none()
    if not creator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")
    if body.priority is not None:
        creator.priority = body.priority
    if body.display_name is not None:
        creator.display_name = body.display_name
    await session.flush()
    await session.refresh(creator, ["platforms"])
    return CreatorRead.model_validate(creator)


@router.delete(
    "/{creator_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_creator(
    creator_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    result = await session.execute(
        select(Creator).where(Creator.id == creator_id, Creator.user_id == current_user.id)
    )
    creator = result.scalar_one_or_none()
    if not creator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")
    await session.delete(creator)
    await session.flush()
