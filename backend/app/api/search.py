from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.source import Source
from app.models.user import User
from app.utils.search import search_content
from app.utils.logging import get_logger

router = APIRouter(prefix="/search", tags=["search"])
logger = get_logger(__name__)


@router.get("")
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Scope search to user's sources only
    result = await session.execute(
        select(Source.id).where(Source.user_id == current_user.id, Source.is_active == True)
    )
    source_ids = [str(row[0]) for row in result.fetchall()]

    hits = await search_content(
        query=q,
        user_source_ids=source_ids,
        limit=limit,
        offset=offset,
    )
    return {"query": q, "hits": hits, "limit": limit, "offset": offset}
