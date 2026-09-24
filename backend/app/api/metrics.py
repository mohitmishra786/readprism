from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.services.metrics import analytics
from app.services.ranking.evaluation import evaluate_user_ranking

router = APIRouter(prefix="/metrics", tags=["metrics"])
settings = get_settings()


async def require_metrics_token(x_metrics_token: str | None = Header(default=None)) -> None:
    """Gate aggregate/operator metrics behind a shared token.

    Required outside development; open in development for convenience. Prevents
    any authenticated user from reading whole-instance analytics on a hosted
    deployment.
    """
    if not settings.metrics_token:
        if settings.app_env == "development":
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Metrics endpoint not configured"
        )
    if x_metrics_token != settings.metrics_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid metrics token"
        )


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


@router.get("/north-star", dependencies=[Depends(require_metrics_token)])
async def north_star(
    days: int = Query(30, ge=1, le=365), session: AsyncSession = Depends(get_db)
) -> dict:
    """Suggestion-driven-read rate — the single flywheel/PMF indicator."""
    return await analytics.suggestion_read_rate(session, days=days)


@router.get("/cold-start-funnel", dependencies=[Depends(require_metrics_token)])
async def cold_start_funnel(session: AsyncSession = Depends(get_db)) -> dict:
    return await analytics.cold_start_funnel(session)


@router.get("/cohort-retention", dependencies=[Depends(require_metrics_token)])
async def cohort_retention(session: AsyncSession = Depends(get_db)) -> list[dict]:
    return await analytics.cohort_retention(session)


@router.get("/scraper-health", dependencies=[Depends(require_metrics_token)])
async def scraper_health(session: AsyncSession = Depends(get_db)) -> dict:
    return await analytics.scraper_health(session)


@router.get("/meta-weight-divergence", dependencies=[Depends(require_metrics_token)])
async def meta_weight_divergence(session: AsyncSession = Depends(get_db)) -> dict:
    return await analytics.meta_weight_divergence(session)


@router.get("/email-deliverability", dependencies=[Depends(require_metrics_token)])
async def email_deliverability() -> dict:
    return await analytics.email_deliverability()


@router.post("/recompute-scores", dependencies=[Depends(require_metrics_token)])
async def recompute_scores(session: AsyncSession = Depends(get_db)) -> dict:
    """List items the ranker version should rescore. The Celery task does the write."""
    from app.models.content import ContentItem
    from app.services.ranking.phase2.learning import RANKER_VERSION

    ids = (await session.execute(select(ContentItem.id))).scalars().all()
    return {"ranker_version": RANKER_VERSION, "items": len(ids)}


@router.get("/ingestion", dependencies=[Depends(require_metrics_token)])
async def ingestion_metrics(session: AsyncSession = Depends(get_db)) -> dict:
    """Fetch success, extraction method mix, and ingest-to-score lag."""
    from app.models.content import ContentItem
    from app.models.source import Source
    from app.services.ingestion.observe import ingestion_report
    from app.services.ingestion.retention import storage_stats

    sources = list((await session.execute(select(Source))).scalars())
    items = list((await session.execute(select(ContentItem))).scalars())
    report = ingestion_report(sources, items)
    report["storage"] = storage_stats(
        [
            {
                "id": item.id,
                "source_id": item.source_id,
                "text_length": len(item.full_text or ""),
            }
            for item in items
        ]
    )
    return report
