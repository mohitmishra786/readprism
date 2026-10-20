"""Online embedding model re-embed service (#244).

Re-encodes content items whose stored vector model does not match the active model.
Processes rows in id-ordered batches, committing per batch, with a resumable cursor
stored in Redis.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.services.embeddings.registry import EmbeddingSpec
from app.services.embeddings.text import embedding_pieces, pool_vectors
from app.utils.cache import cache_get, cache_set
from app.utils.logging import get_logger

logger = get_logger(__name__)

REDIS_CURSOR_KEY = "reembed:cursor"


async def get_reembed_cursor() -> str | None:
    val = await cache_get(REDIS_CURSOR_KEY)
    return str(val) if val else None


async def set_reembed_cursor(cursor: str | None) -> None:
    if cursor is None:
        from app.utils.cache import get_redis

        try:
            r = get_redis()
            await r.delete(REDIS_CURSOR_KEY)
        except Exception:
            pass
    else:
        await cache_set(REDIS_CURSOR_KEY, cursor, ttl_seconds=30 * 24 * 3600)


async def reembed_batch(
    session: AsyncSession,
    active: EmbeddingSpec,
    batch_size: int = 200,
    cursor: str | None = None,
    encoder: Any = None,
) -> dict[str, Any]:
    """Re-encode one batch of outdated items in id order and commit."""
    query = (
        select(ContentItem)
        .where(
            ContentItem.embedding.is_not(None),
            or_(
                ContentItem.embedding_model != active.name,
                ContentItem.embedding_model.is_(None),
            ),
        )
        .order_by(ContentItem.id.asc())
        .limit(batch_size)
    )
    if cursor:
        try:
            cursor_uuid = uuid.UUID(cursor)
            query = query.where(ContentItem.id > cursor_uuid)
        except (ValueError, TypeError):
            pass

    items = list((await session.execute(query)).scalars().all())

    if not items:
        # Check if any outdated rows remain from the beginning
        remaining_count = await session.scalar(
            select(ContentItem.id)
            .where(
                ContentItem.embedding.is_not(None),
                or_(
                    ContentItem.embedding_model != active.name,
                    ContentItem.embedding_model.is_(None),
                ),
            )
            .limit(1)
        )
        if remaining_count is None:
            await set_reembed_cursor(None)
            return {"reembedded": 0, "next_cursor": None, "done": True}
        # Reset cursor to start next pass
        await set_reembed_cursor(None)
        return {"reembedded": 0, "next_cursor": None, "done": False}

    for item in items:
        pieces = embedding_pieces(
            title=item.title or "",
            lead=item.summary_brief or "",
            body=item.full_text or "",
        )
        if not pieces:
            # Fall back to title or URL
            pieces = [item.title or item.url or "untitled"]

        if encoder is not None:
            if hasattr(encoder, "encode_batch_cached"):
                encoded = await encoder.encode_batch_cached(pieces)
            elif callable(encoder):
                encoded = [encoder(p) for p in pieces]
            else:
                encoded = [encoder.encode([p])[0].tolist() for p in pieces]
        else:
            from app.utils.embeddings import get_embedding_service

            svc = get_embedding_service()
            encoded = await svc.encode_batch_cached(pieces)

        embedding = pool_vectors(encoded)
        item.embedding = embedding
        item.embedding_model = active.name
        item.embedding_dim = len(embedding)
        item.embedding_version = active.version

    await session.commit()

    next_cursor = str(items[-1].id)
    await set_reembed_cursor(next_cursor)
    done = len(items) < batch_size

    return {
        "reembedded": len(items),
        "next_cursor": next_cursor,
        "done": done,
    }
