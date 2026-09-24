from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.content import ContentItem
from app.models.source import Source
from app.models.user import User
from app.schemas.source import SourceCreate, SourceRead, SourceUpdate
from app.services.entitlements import enforce_source_limit
from app.services.ingestion.rss_parser import _autodiscover_feed
from app.utils.logging import get_logger
from app.utils.xml_safety import UnsafeXMLError, assert_xml_safe

router = APIRouter(prefix="/sources", tags=["sources"])
logger = get_logger(__name__)


@router.post("", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
async def add_source(
    body: SourceCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SourceRead:
    # Enforce the free-tier source limit (audit 13-1/13-5).
    count = (
        await session.execute(
            select(func.count()).select_from(Source).where(Source.user_id == current_user.id)
        )
    ).scalar() or 0
    enforce_source_limit(current_user, count)

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
        initial_backfill_done=False,
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
    sources = list(result.scalars().all())
    counts = await _items_per_week(session, [s.id for s in sources])
    rows = []
    for source in sources:
        row = SourceRead.model_validate(source)
        row.items_per_week = counts.get(source.id, 0)
        rows.append(row)
    return rows


async def _items_per_week(session: AsyncSession, source_ids: list) -> dict:
    if not source_ids:
        return {}
    cutoff = datetime.now(UTC) - timedelta(days=7)
    result = await session.execute(
        select(ContentItem.source_id, func.count())
        .where(ContentItem.source_id.in_(source_ids), ContentItem.fetched_at >= cutoff)
        .group_by(ContentItem.source_id)
    )
    return {row[0]: int(row[1]) for row in result.all()}


# Static path must be registered before /{source_id} to prevent shadowing
@router.post("/import-opml", response_model=dict)
async def import_opml(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    content = await file.read()
    limits = get_settings()
    try:
        opml_bytes = assert_xml_safe(
            content,
            max_bytes=limits.xml_max_bytes,
            max_outlines=limits.opml_max_outlines,
        )
    except UnsafeXMLError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    opml_text = opml_bytes.decode("utf-8", errors="replace")

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


@router.post("/import-opml-v2", response_model=dict)
async def import_opml_tagged(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Folders become tags, duplicate URLs are skipped, large files are queued."""
    content = await file.read()
    limits = get_settings()
    try:
        opml_bytes = assert_xml_safe(
            content,
            max_bytes=limits.xml_max_bytes,
            max_outlines=limits.opml_max_outlines,
        )
    except UnsafeXMLError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    from app.services.ingestion.opml_io import plan_import

    existing = await session.execute(select(Source.url).where(Source.user_id == current_user.id))
    plan = plan_import(opml_bytes.decode("utf-8", errors="replace"), {row[0] for row in existing})
    for feed in plan.feeds:
        session.add(
            Source(
                user_id=current_user.id,
                url=feed.url,
                name=feed.title,
                feed_url=feed.url,
                source_type="rss",
                tags=feed.tags,
                initial_backfill_done=False,
            )
        )
    await session.flush()
    return {
        "created": plan.created,
        "skipped": plan.skipped,
        "queued": plan.queued,
        "progress": plan.progress,
    }


@router.get("/export-opml")
async def export_opml_file(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    from app.services.ingestion.opml_io import OpmlFeed, export_opml

    result = await session.execute(select(Source).where(Source.user_id == current_user.id))
    feeds = [
        OpmlFeed(
            url=source.feed_url or source.url,
            title=source.name or source.url,
            tags=list(source.tags or []),
        )
        for source in result.scalars()
    ]
    body = export_opml(feeds)
    return Response(content=body, media_type="application/xml")


@router.post("/import-saved", response_model=dict)
async def import_saved(
    kind: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.models.content import ContentItem, UserContentInteraction
    from app.services.ingestion.importers import import_csv, import_opml_starred

    raw = (await file.read()).decode("utf-8", errors="replace")
    if kind == "opml":
        imported = import_opml_starred(raw)
    else:
        try:
            imported = import_csv(raw, kind)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    created = 0
    for item in imported:
        if not item.url:
            continue
        exists = await session.execute(select(ContentItem.id).where(ContentItem.url == item.url))
        if exists.scalar_one_or_none():
            continue
        row = ContentItem(
            owner_user_id=current_user.id,
            url=item.url,
            title=item.title,
            full_text=item.note,
            origin="import",
        )
        session.add(row)
        await session.flush()
        session.add(
            UserContentInteraction(
                user_id=current_user.id,
                content_item_id=row.id,
                saved=True,
                explicit_rating=1,
            )
        )
        created += 1
    await session.flush()
    return {"created": created, "origin": "import"}


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


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
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
