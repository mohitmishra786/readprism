from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.content import ContentItem
from app.models.source import Source
from app.models.user import User
from app.services.search.hybrid import rrf_fuse
from app.utils.logging import get_logger

router = APIRouter(prefix="/search", tags=["search"])
logger = get_logger(__name__)

# Per-leg candidate depth before fusion.
FUSION_CANDIDATES = 60


async def _fts_ids(
    session: AsyncSession,
    query: str,
    filters_sql: str,
    params: dict,
    limit: int,
) -> list[str]:
    sql = text(
        f"""
        SELECT ci.id::text
        FROM content_items ci
        WHERE ci.search_tsv @@ websearch_to_tsquery('english', :query)
          {filters_sql}
        ORDER BY ts_rank(ci.search_tsv, websearch_to_tsquery('english', :query)) DESC
        LIMIT :limit
        """
    )
    rows = await session.execute(sql, {**params, "query": query, "limit": limit})
    return [row[0] for row in rows.all()]


async def _vector_ids(
    session: AsyncSession,
    query_embedding: list[float],
    filters_sql: str,
    params: dict,
    limit: int,
    *,
    model_name: str,
    model_dim: int,
) -> list[str]:
    # Same-model guard: only rows embedded by the query's embedder participate.
    sql = text(
        f"""
        SELECT ci.id::text
        FROM content_items ci
        WHERE ci.embedding IS NOT NULL
          AND ci.embedding_model = :model_name AND ci.embedding_dim = :model_dim
          {filters_sql}
        ORDER BY ci.embedding <=> CAST(:vec AS vector)
        LIMIT :limit
        """
    )
    rows = await session.execute(
        sql,
        {
            **params,
            "vec": str(query_embedding),
            "model_name": model_name,
            "model_dim": model_dim,
            "limit": limit,
        },
    )
    return [row[0] for row in rows.all()]


@router.get("")
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    source_id: uuid.UUID | None = Query(None, description="Restrict to one source"),
    saved: bool | None = Query(None, description="Only items the user saved"),
    origin: str | None = Query(None, description="followed | discovery | import"),
    since_days: int | None = Query(
        None, ge=1, le=3650, description="Only items fetched in the last N days"
    ),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Hybrid search over the user's archive (UX-11).

    Postgres FTS (weighted tsvector) + pgvector semantic, fused with
    Reciprocal Rank Fusion. Filters apply inside both legs.
    """
    # Scope: the user's feeds (#108: including other subscribers' source rows
    # for the same feed, which hold the shared items), never other users'
    # private items.
    from app.services.feed_identity import equivalent_source_ids, feed_key, user_feed_ids

    source_ids = await equivalent_source_ids(session, current_user.id)
    feed_ids = await user_feed_ids(session, current_user.id) if source_id is None else []
    if source_id is not None:
        own = (
            await session.execute(
                select(feed_key()).where(Source.id == source_id, Source.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if own is None:
            source_ids = []
        else:
            same_feed = await session.execute(select(Source.id).where(feed_key() == own))
            wanted = {row[0] for row in same_feed.all()}
            source_ids = [sid for sid in source_ids if sid in wanted]

    filters: list[str] = [
        "(ci.source_id = ANY(:source_ids) OR ci.feed_id = ANY(:feed_ids))",
        "(ci.owner_user_id IS NULL OR ci.owner_user_id = :viewer)",
    ]
    params: dict = {
        "source_ids": [str(s) for s in source_ids],
        "feed_ids": [str(f) for f in feed_ids],
        "viewer": str(current_user.id),
    }
    if origin is not None:
        filters.append("ci.origin = :origin")
        params["origin"] = origin
    if since_days is not None:
        filters.append("ci.fetched_at >= :since")
        params["since"] = datetime.now(UTC) - timedelta(days=since_days)
    if saved is not None:
        filters.append(
            "EXISTS (SELECT 1 FROM user_content_interactions uci "
            "WHERE uci.content_item_id = ci.id AND uci.user_id = :uid AND uci.saved = :saved)"
        )
        params["saved"] = saved
        params["uid"] = str(current_user.id)
    from app.services.takedown import raw_not_blocked_sql

    filters_sql = " AND " + " AND ".join(filters) + raw_not_blocked_sql("ci")

    # Per-leg candidate depth must cover the requested page: an offset beyond
    # a fixed candidate window would return an empty page even when scoped
    # matches exist (CodeRabbit).
    depth = max(FUSION_CANDIDATES, offset + limit)
    fts_list = await _fts_ids(session, q, filters_sql, params, depth)

    vector_list: list[str] = []
    if source_ids or feed_ids:
        try:
            # The query must come from the same embedder as the items
            # (#311): MiniLM on the standard image, the hash fallback on lite.
            # A hash query against MiniLM item vectors ranked at random.
            from app.utils.embeddings import get_embedding_service

            embedder = get_embedding_service()
            query_vec = await embedder.encode_single(q)
            vector_list = await _vector_ids(
                session,
                query_vec,
                filters_sql,
                params,
                depth,
                model_name=embedder.model_name,
                model_dim=embedder.dimension,
            )
        except Exception as e:
            logger.warning(f"Vector leg skipped (non-fatal): {e}")

    fused = rrf_fuse(fts_list, vector_list)
    page = fused[offset : offset + limit]
    has_more = offset + limit < len(fused)
    if not page:
        return {"query": q, "hits": [], "limit": limit, "offset": offset, "has_more": has_more}

    from app.services.takedown import not_blocked_filter

    rows = await session.execute(
        select(ContentItem).where(
            ContentItem.id.in_([uuid.UUID(p) for p in page]), not_blocked_filter()
        )
    )
    by_id = {item.id: item for item in rows.scalars().all()}
    ordered = [by_id[uuid.UUID(item_id)] for item_id in page if uuid.UUID(item_id) in by_id]

    return {
        "query": q,
        "hits": [
            {
                "id": str(item.id),
                "title": item.title,
                "url": item.url,
                "author": item.author,
                "summary_headline": item.summary_headline,
                "summary_brief": item.summary_brief,
                "source_id": str(item.source_id) if item.source_id else None,
                "origin": item.origin,
                "topic_clusters": item.topic_clusters or [],
                "reading_time_minutes": item.reading_time_minutes,
                "published_at": item.published_at.isoformat() if item.published_at else None,
            }
            for item in ordered
        ],
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < len(fused),
    }


@router.get("/why/{content_id}")
async def why_not_seen(
    content_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """'Why didn't I see this?' (#267): the item's live score for this user,
    each signal's contribution in the digest's wording, whether and when it
    was in a digest (and if not, why not), and what would raise it."""
    from app.services.ranking.why_not import explain_item_id

    result = await explain_item_id(current_user, content_id, session)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content item not found")
    return result
