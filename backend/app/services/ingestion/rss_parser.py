from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx

from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RawContentItem:
    url: str
    title: str
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    full_text: Optional[str] = None
    word_count: Optional[int] = None
    source_feed_url: Optional[str] = None
    creator_platform_id: Optional[str] = None


def _count_words(text: str) -> int:
    return len(text.split()) if text else 0


def _extract_text(entry: feedparser.FeedParserDict) -> str:
    if hasattr(entry, "content") and entry.content:
        return entry.content[0].get("value", "")
    if hasattr(entry, "summary"):
        return entry.summary or ""
    return ""


def _parse_date(entry: feedparser.FeedParserDict) -> Optional[datetime]:
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        value = getattr(entry, attr, None)
        if value:
            try:
                import calendar
                # struct_time from feedparser is in UTC; convert to aware datetime
                ts = calendar.timegm(value)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except Exception:
                pass
    return None


async def _autodiscover_feed(page_url: str) -> Optional[str]:
    common_paths = ["/feed", "/rss", "/atom.xml", "/feed.xml", "/rss.xml", "/feed/rss"]
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(page_url)
            html = resp.text
            # Try to find <link rel="alternate" type="application/rss+xml">
            pattern = r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*href=["\']([^"\']+)["\']'
            matches = re.findall(pattern, html, re.IGNORECASE)
            if matches:
                href = matches[0]
                if href.startswith("http"):
                    return href
                from urllib.parse import urljoin
                return urljoin(page_url, href)
    except Exception as e:
        logger.debug(f"Autodiscover HTML parse failed for {page_url}: {e}")

    from urllib.parse import urlparse, urljoin
    parsed = urlparse(page_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for path in common_paths:
            try:
                url = urljoin(base, path)
                resp = await client.get(url)
                if resp.status_code == 200 and ("rss" in resp.text[:500].lower() or "atom" in resp.text[:500].lower() or "<feed" in resp.text[:500].lower()):
                    return url
            except Exception:
                pass
    return None


async def parse_feed(url: str) -> list[RawContentItem]:
    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            discovered = await _autodiscover_feed(url)
            if discovered:
                feed = feedparser.parse(discovered)

        items: list[RawContentItem] = []
        for entry in feed.entries:
            link = getattr(entry, "link", None)
            title = getattr(entry, "title", "Untitled")
            if not link:
                continue
            text = _extract_text(entry)
            word_count = _count_words(text) if text else None
            items.append(RawContentItem(
                url=link,
                title=title,
                author=getattr(entry, "author", None),
                published_at=_parse_date(entry),
                full_text=text or None,
                word_count=word_count,
                source_feed_url=url,
            ))
        return items
    except Exception as e:
        logger.error(f"Failed to parse feed {url}: {e}")
        return []
