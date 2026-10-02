from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.ranking import OnboardingRequest
from app.services.cold_start.onboarding import SampleRating as ServiceSampleRating
from app.services.cold_start.onboarding import process_onboarding
from app.utils.logging import get_logger

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
logger = get_logger(__name__)


class ExpandInterestsRequest(BaseModel):
    interest_text: str = Field(..., min_length=3, max_length=4000)


@router.post("/expand-interests")
async def expand_interests(
    body: ExpandInterestsRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """CS-01 step 1: expand free-text interests into subtopics the user
    confirms/edits before onboarding continues. Without an LLM the keyword
    fallback still returns topics — the flow never blocks."""
    from app.services.cold_start.onboarding import _fallback_topic_extract
    from app.services.summarization.groq_client import GroqSummarizer

    topics: list[str] = []
    try:
        topics = await GroqSummarizer().expand_interests(body.interest_text)
    except Exception as e:
        logger.info(f"Interest expansion fell back to keywords: {e}")
    if not topics:
        topics = _fallback_topic_extract(body.interest_text)
    return {"topics": topics}


class CalibrationRating(BaseModel):
    rating: int  # 1 = more like this, -1 = less like this


@router.get("/calibration")
async def get_calibration_items(
    limit: int = 10,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """CS-03: a diverse sample of the user's freshly ingested items for quick
    ratings after the first backfill."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.models.content import ContentItem
    from app.models.source import Source
    from app.services.cold_start.calibration import select_calibration_items

    source_ids_result = await session.execute(
        select(Source.id).where(Source.user_id == current_user.id, Source.is_active == True)
    )
    source_ids = [row[0] for row in source_ids_result.fetchall()]
    if not source_ids:
        return []

    cutoff = datetime.now(UTC) - timedelta(days=7)
    items_result = await session.execute(
        select(ContentItem)
        .where(
            ContentItem.source_id.in_(source_ids),
            ContentItem.fetched_at >= cutoff,
            ContentItem.rankable.is_(True),
        )
        .order_by(ContentItem.fetched_at.desc())
        .limit(100)
    )
    items = list(items_result.scalars().all())
    if not items:
        return []

    k = max(8, min(12, limit))
    picks = select_calibration_items([item.embedding for item in items], k=k)
    return [
        {
            "id": str(items[p.index].id),
            "title": items[p.index].title,
            "url": items[p.index].url,
            "topic_clusters": items[p.index].topic_clusters or [],
            "reading_time_minutes": items[p.index].reading_time_minutes,
        }
        for p in picks
    ]


@router.post("/calibration/{content_id}")
async def rate_calibration_item(
    content_id: uuid.UUID,
    body: CalibrationRating,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Rate a calibration item; matching clusters update immediately (CS-03)."""
    from sqlalchemy import select

    from app.models.content import ContentItem
    from app.models.interest_graph import InterestNode

    if body.rating not in (1, -1):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="rating must be 1 or -1"
        )

    item_result = await session.execute(select(ContentItem).where(ContentItem.id == content_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content item not found")

    # Reinforce/suppress every cluster node the item belongs to.
    delta = 0.25 if body.rating == 1 else -0.25
    updated = 0
    for label in item.topic_clusters or []:
        node_result = await session.execute(
            select(InterestNode).where(
                InterestNode.user_id == current_user.id,
                InterestNode.topic_label == label,
            )
        )
        node = node_result.scalar_one_or_none()
        if node is None:
            continue
        node.weight = max(0.0, min(1.0, node.weight + delta))
        updated += 1

    await session.flush()
    return {"status": "ok", "clusters_updated": updated}


@router.post("", status_code=status.HTTP_200_OK)
async def complete_onboarding(
    body: OnboardingRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.onboarding_complete:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Onboarding already completed",
        )

    sample_ratings = [
        ServiceSampleRating(
            article_url=r.article_url,
            title=r.title,
            rating=r.rating,
        )
        for r in body.sample_ratings
    ]

    await process_onboarding(
        user=current_user,
        interest_text=body.interest_text,
        sample_ratings=sample_ratings,
        source_opml=body.source_opml,
        session=session,
        confirmed_topics=body.confirmed_topics,
    )
    await session.commit()

    return {"status": "ok", "message": "Onboarding complete"}
