"""Resolve a URL to the content row a given user may use (#101).

A URL can exist once as a public row (feeds, scraping) and once per user as
a private row (extension saves, imports, newsletters). Other users' private
rows are invisible: never returned, never mentioned in an error, never
linked to someone else's interactions.
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem


def visible_to(user_id: uuid.UUID):
    """SQL filter: public rows plus this user's private rows."""
    return or_(ContentItem.owner_user_id.is_(None), ContentItem.owner_user_id == user_id)


async def find_visible_item(
    session: AsyncSession, user_id: uuid.UUID, url: str
) -> ContentItem | None:
    """The public row for `url` if one exists, else this user's private row."""
    result = await session.execute(
        select(ContentItem)
        .where(ContentItem.url == url, visible_to(user_id))
        # Prefer the shared public row: it carries the shared summary/embedding.
        .order_by(ContentItem.owner_user_id.is_(None).desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_or_create_private_item(
    session: AsyncSession,
    user_id: uuid.UUID,
    url: str,
    *,
    title: str,
    origin: str,
    full_text: str | None = None,
) -> tuple[ContentItem, bool]:
    """Return (item, created). Reuses a visible row; otherwise creates a private one."""
    from datetime import UTC, datetime

    existing = await find_visible_item(session, user_id, url)
    if existing is not None:
        return existing, False
    item = ContentItem(
        url=url,
        title=title or url,
        origin=origin,
        owner_user_id=user_id,
        full_text=full_text,
        fetched_at=datetime.now(UTC),
        rankable=True,
    )
    session.add(item)
    await session.flush()
    return item, True
