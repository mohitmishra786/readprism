"""Instance-wide takedown list (#183).

Normalizes targets (URLs and hosts), adds/removes takedowns, and provides
filters for queries so blocked content disappears immediately without restarts.
"""

from __future__ import annotations

from urllib.parse import urlparse

import sqlalchemy as sa
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blocked_url import BlockedUrl
from app.models.content import ContentItem
from app.services.ingestion.canonicalize import canonicalize_url
from app.utils.logging import get_logger

logger = get_logger(__name__)


def normalize_target(target: str, is_host: bool | None = None) -> str:
    """Normalize a URL or a hostname.

    If is_host is True, or if the string has no scheme or an empty path, it is
    treated as a host (lower-cased, www. stripped). Otherwise, it is canonicalized
    as a URL.
    """
    raw = target.strip()
    if not raw:
        return ""

    if is_host is True:
        return _normalize_host(raw)

    if is_host is False:
        canonical = canonicalize_url(raw)
        return canonical or raw

    # Auto-detect: if no scheme, or scheme with no path or only '/', treat as host.
    if "://" not in raw:
        return _normalize_host(raw)

    parsed = urlparse(raw)
    path = parsed.path.strip()
    if (not path or path == "/") and not parsed.query:
        return _normalize_host(parsed.hostname or raw)

    canonical = canonicalize_url(raw)
    return canonical or raw


def _normalize_host(host_str: str) -> str:
    h = host_str.strip().lower()
    if "://" in h:
        parsed = urlparse(h)
        h = parsed.hostname or h
    if h.startswith("www."):
        h = h[4:]
    return h.strip("/")


async def add_blocked_entry(
    session: AsyncSession, target: str, reason: str, is_host: bool | None = None
) -> BlockedUrl:
    """Add or update a takedown entry."""
    key = normalize_target(target, is_host)
    if not key:
        raise ValueError("Cannot block an empty URL or host")

    result = await session.execute(select(BlockedUrl).where(BlockedUrl.url_key == key))
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.reason = reason
        await session.flush()
        return existing

    entry = BlockedUrl(url_key=key, reason=reason)
    session.add(entry)
    await session.flush()
    return entry


async def remove_blocked_entry(
    session: AsyncSession, target: str, is_host: bool | None = None
) -> bool:
    """Remove a takedown entry. Returns True if removed, False if not found."""
    key = normalize_target(target, is_host)
    result = await session.execute(select(BlockedUrl).where(BlockedUrl.url_key == key))
    existing = result.scalar_one_or_none()
    if existing is None:
        return False
    await session.delete(existing)
    await session.flush()
    return True


async def is_url_blocked(session: AsyncSession, url: str) -> bool:
    """Check if a URL or its host is on the takedown list."""
    if not url:
        return False
    canonical = canonicalize_url(url) or url
    host = _normalize_host(url)

    # The host and every parent domain: a block on "b.example.com" covers
    # "a.b.example.com" too (the SQL filter matches the same way).
    host_parts = host.split(".")
    candidates = [".".join(host_parts[i:]) for i in range(len(host_parts) - 1)] or [host]

    q = (
        select(BlockedUrl.id)
        .where(
            or_(
                BlockedUrl.url_key == canonical,
                BlockedUrl.url_key == url,
                BlockedUrl.url_key.in_(candidates),
            )
        )
        .limit(1)
    )
    res = await session.execute(q)
    return res.scalar_one_or_none() is not None


def not_blocked_filter():
    """SQLAlchemy condition: ContentItem is not blocked by URL or host."""
    return ~sa.exists(
        select(BlockedUrl.id).where(
            or_(
                ContentItem.url == BlockedUrl.url_key,
                and_(
                    ~BlockedUrl.url_key.contains("/"),
                    or_(
                        ContentItem.url.ilike(func.concat("%://", BlockedUrl.url_key, "/%")),
                        ContentItem.url.ilike(func.concat("%://", BlockedUrl.url_key)),
                        ContentItem.url.ilike(func.concat("%://%.", BlockedUrl.url_key, "/%")),
                        ContentItem.url.ilike(func.concat("%://%.", BlockedUrl.url_key)),
                        ContentItem.url.ilike(func.concat("%://www.", BlockedUrl.url_key, "/%")),
                        ContentItem.url.ilike(func.concat("%://www.", BlockedUrl.url_key)),
                    ),
                ),
            )
        )
    )


def raw_not_blocked_sql(alias: str = "ci") -> str:
    """Raw SQL snippet for excluding blocked items in text queries."""
    return f"""
    AND NOT EXISTS (
        SELECT 1 FROM blocked_urls bu
        WHERE {alias}.url = bu.url_key
           OR (
               bu.url_key NOT LIKE '%/%'
               AND (
                   {alias}.url ILIKE '%://' || bu.url_key || '/%'
                   OR {alias}.url ILIKE '%://' || bu.url_key
                   OR {alias}.url ILIKE '%://%.' || bu.url_key || '/%'
                   OR {alias}.url ILIKE '%://%.' || bu.url_key
                   OR {alias}.url ILIKE '%://www.' || bu.url_key || '/%'
                   OR {alias}.url ILIKE '%://www.' || bu.url_key
               )
           )
    )
    """
