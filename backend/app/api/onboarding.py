from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.ranking import OnboardingRequest, SampleRating as SchemaSampleRating
from app.services.cold_start.onboarding import SampleRating as ServiceSampleRating, process_onboarding
from app.utils.logging import get_logger

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
logger = get_logger(__name__)


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
    )
    await session.commit()

    return {"status": "ok", "message": "Onboarding complete"}
