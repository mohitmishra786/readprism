"""Feed identity across users' source rows (#108, interim until #86).

Sources are per-user rows, but a public content item is stored once, under
whichever subscriber's source ingested it first. Two users following the same
feed therefore have different `source_id`s while sharing items. These helpers
treat sources with the same feed key as one feed:

- "my items" = items under any source with the same feed key as one of mine
  (public items, plus my own private ones);
- per-user source state (trust, tags) always comes from the user's own row.

The feed key is `coalesce(feed_url, url)`. The shared-feeds epic (#86)
replaces this with a real `feeds` table.
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, false, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.source import Source


def feed_key():
    return func.coalesce(Source.feed_url, Source.url)


def _user_feed_keys(user_id: uuid.UUID, *, active_only: bool):
    q = select(feed_key()).where(Source.user_id == user_id)
    if active_only:
        q = q.where(Source.is_active == True)
    return q


async def equivalent_source_ids(
    session: AsyncSession, user_id: uuid.UUID, *, active_only: bool = True
) -> list[uuid.UUID]:
    """Ids of every source row (any user) sharing a feed with this user's sources."""
    result = await session.execute(
        select(Source.id).where(feed_key().in_(_user_feed_keys(user_id, active_only=active_only)))
    )
    return [row[0] for row in result.all()]


def visible_item_filter(user_id: uuid.UUID):
    """Public items, or private items owned by this user."""
    return or_(ContentItem.owner_user_id.is_(None), ContentItem.owner_user_id == user_id)


async def user_source_for_item(
    session: AsyncSession, user_id: uuid.UUID, source_id: uuid.UUID | None
) -> Source | None:
    """This user's own source row for the feed an item came from, if they follow it."""
    if source_id is None:
        return None
    origin = await session.get(Source, source_id)
    if origin is None:
        return None
    if origin.user_id == user_id:
        return origin
    key = origin.feed_url or origin.url
    result = await session.execute(
        select(Source)
        .where(Source.user_id == user_id, feed_key() == key)
        .order_by(Source.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def user_feed_ids(session: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    """Shared feeds this user actively subscribes to (#161)."""
    result = await session.execute(
        select(Source.feed_id).where(
            Source.user_id == user_id, Source.is_active == True, Source.feed_id.isnot(None)
        )
    )
    return [row[0] for row in result.all() if row[0] is not None]


def from_user_feeds(source_ids: list[uuid.UUID], feed_ids: list[uuid.UUID]):
    """Items filed under any equivalent source row, or tagged with one of the
    user's feeds (survives deletion of the subscriber row that stored them)."""
    return or_(
        ContentItem.source_id.in_(source_ids) if source_ids else false(),
        ContentItem.feed_id.in_(feed_ids) if feed_ids else false(),
    )


def outside_user_feeds(source_ids: list[uuid.UUID], feed_ids: list[uuid.UUID]):
    """Negation of from_user_feeds that treats NULLs as 'outside'."""
    return and_(
        or_(ContentItem.source_id.is_(None), ContentItem.source_id.notin_(source_ids))
        if source_ids
        else true(),
        or_(ContentItem.feed_id.is_(None), ContentItem.feed_id.notin_(feed_ids))
        if feed_ids
        else true(),
    )
