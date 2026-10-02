from __future__ import annotations

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
