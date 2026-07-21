from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.ranking.evaluation import evaluate_user_ranking

router = APIRouter(prefix="/metrics", tags=["metrics"])


class RankingEvalRead(BaseModel):
    n: int
    read_prediction_auc: float | None
    spearman_completion: float | None
    positives: int


@router.get("/ranking-eval", response_model=RankingEvalRead)
async def ranking_eval(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RankingEvalRead:
    """How well did the PRS predict *your* reads over the last N days?

    read_prediction_auc > 0.5 means the ranking beats chance at predicting what
    you open; ~0.5 means it isn't learning your behaviour yet.
    """
    result = await evaluate_user_ranking(current_user.id, session, days=days)
    return RankingEvalRead(
        n=result.n,
        read_prediction_auc=result.read_prediction_auc,
        spearman_completion=result.spearman_completion,
        positives=result.positives,
    )
