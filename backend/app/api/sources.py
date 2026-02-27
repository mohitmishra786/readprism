from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.source import Source
from app.models.user import User
from app.schemas.source import SourceCreate, SourceRead, SourceUpdate
from app.services.ingestion.rss_parser import _autodiscover_feed
from app.utils.logging import get_logger

router = APIRouter(prefix="/sources", tags=["sources"])
logger = get_logger(__name__)


@router.post("", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
async def add_source(
    body: SourceCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SourceRead:
    # Autodiscover feed URL
    feed_url = await _autodiscover_feed(body.url)
    source_type = "rss" if feed_url else "scraped"

    source = Source(
        user_id=current_user.id,
        url=body.url,
        feed_url=feed_url,
        source_type=source_type,
        priority=body.priority,
        topics=body.topics,
    )
    session.add(source)
    await session.flush()

    # Enqueue initial ingestion
    from app.workers.tasks.ingest_feeds import ingest_all_feeds
    ingest_all_feeds.delay()

    return SourceRead.model_validate(source)


@router.get("", response_model=list[SourceRead])
async def list_sources(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SourceRead]:
    result = await session.execute(select(Source).where(Source.user_id == current_user.id))
    return [SourceRead.model_validate(s) for s in result.scalars().all()]


# Static path must be registered before /{source_id} to prevent shadowing
@router.post("/import-opml", response_model=dict)
async def import_opml(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    content = await file.read()
    opml_text = content.decode("utf-8", errors="replace")

    try:
        import listparser
        result = listparser.parse(opml_text)
        created = 0
        for feed in result.feeds:
            url = feed.url or feed.feed or ""
            if not url:
                continue
            source = Source(
                user_id=current_user.id,
                url=url,
                name=feed.title or url,
                feed_url=url,
                source_type="rss",
            )
            session.add(source)
            created += 1
        await session.flush()
        return {"created": created}
    except ImportError:
        raise HTTPException(status_code=500, detail="listparser not installed")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OPML parse error: {e}")


@router.put("/{source_id}", response_model=SourceRead)
async def update_source(
    source_id: uuid.UUID,
    body: SourceUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SourceRead:
    result = await session.execute(
        select(Source).where(Source.id == source_id, Source.user_id == current_user.id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")

    if body.priority is not None:
        source.priority = body.priority
    if body.trust_weight is not None:
        source.trust_weight = max(0.0, min(1.0, body.trust_weight))
    if body.is_active is not None:
        source.is_active = body.is_active
    if body.topics is not None:
        source.topics = body.topics

    await session.flush()
    return SourceRead.model_validate(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    result = await session.execute(
        select(Source).where(Source.id == source_id, Source.user_id == current_user.id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    source.is_active = False
    await session.flush()
