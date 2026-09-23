from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

import feedparser

from app.utils.logging import get_logger, sanitize_log
from app.utils.sanitize import sanitize_stored_html
from app.utils.ssrf import UnsafeURLError, safe_fetch, validate_public_url
from app.utils.xml_safety import UnsafeXMLError, assert_xml_safe

_FEED_HEADERS = {
    "User-Agent": "ReadPrism/1.0 (+https://readprism.app/bot)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
}
_FEED_MAX_BYTES = 2_000_000

logger = get_logger(__name__)


@dataclass
class RawContentItem:
    url: str
    title: str
    author: str | None = None
    published_at: datetime | None = None
    full_text: str | None = None
    word_count: int | None = None
    source_feed_url: str | None = None
    creator_platform_id: str | None = None


def _count_words(text: str) -> int:
    return len(text.split()) if text else 0


def _extract_text(entry: feedparser.FeedParserDict) -> str:
    # Feed content/summary is raw third-party HTML; strip executable markup
    # before it is stored (audit 06-7 defense in depth).
    if hasattr(entry, "content") and entry.content:
        return sanitize_stored_html(entry.content[0].get("value", ""))
    if hasattr(entry, "summary"):
        return sanitize_stored_html(entry.summary or "")
    return ""


def _parse_date(entry: feedparser.FeedParserDict) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        value = getattr(entry, attr, None)
        if value:
            try:
                import calendar

                # struct_time from feedparser is in UTC; convert to aware datetime
                ts = calendar.timegm(value)
                return datetime.fromtimestamp(ts, tz=UTC)
            except Exception:
                pass
    return None


async def _autodiscover_feed(page_url: str) -> str | None:
    common_paths = ["/feed", "/rss", "/atom.xml", "/feed.xml", "/rss.xml", "/feed/rss"]
    try:
        validate_public_url(page_url)
    except UnsafeURLError as e:
        logger.warning(f"Blocked feed autodiscovery for unsafe URL {sanitize_log(page_url)}: {e}")
        return None
    try:
        resp = await safe_fetch(
            page_url, headers=_FEED_HEADERS, timeout=10, max_bytes=_FEED_MAX_BYTES
        )
        html = resp.text
        pattern = (
            r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*href=["\']([^"\']+)["\']'
        )
        matches = re.findall(pattern, html, re.IGNORECASE)
        if matches:
            href = matches[0]
            if href.startswith("http"):
                return href
            from urllib.parse import urljoin

            return urljoin(page_url, href)
    except Exception as e:
        logger.debug(f"Autodiscover HTML parse failed for {sanitize_log(page_url)}: {e}")

    from urllib.parse import urljoin, urlparse

    parsed = urlparse(page_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    for path in common_paths:
        url = urljoin(base, path)
        try:
            resp = await safe_fetch(
                url, headers=_FEED_HEADERS, timeout=10, max_bytes=_FEED_MAX_BYTES
            )
            if resp.status_code == 200 and (
                "rss" in resp.text[:500].lower()
                or "atom" in resp.text[:500].lower()
                or "<feed" in resp.text[:500].lower()
            ):
                return url
        except Exception as e:
            logger.debug(f"Feed probe failed for {sanitize_log(url)}: {e}")
    return None


async def _load_feed_bytes(url: str) -> bytes | None:
    """Fetch a feed through safe_fetch. feedparser must not fetch the URL itself."""
    try:
        validate_public_url(url)
    except UnsafeURLError as e:
        logger.warning("Blocked feed fetch for unsafe URL %s: %s", sanitize_log(url), e)
        return None
    try:
        resp = await safe_fetch(url, headers=_FEED_HEADERS, timeout=20, max_bytes=_FEED_MAX_BYTES)
    except UnsafeURLError as e:
        logger.warning("Blocked feed fetch for %s: %s", sanitize_log(url), e)
        return None
    except Exception as e:
        logger.error("Failed to fetch feed %s: %s", sanitize_log(url), e)
        return None
    if resp.status_code >= 400:
        logger.warning("Feed %s returned HTTP %s", sanitize_log(url), resp.status_code)
        return None
    try:
        return assert_xml_safe(resp.content, max_bytes=_FEED_MAX_BYTES)
    except UnsafeXMLError as e:
        logger.warning("Rejected unsafe feed XML from %s: %s", sanitize_log(url), e)
        return None


async def parse_feed(url: str) -> list[RawContentItem]:
    try:
        body = await _load_feed_bytes(url)
        if body is None:
            return []
        feed = feedparser.parse(body)
        if feed.bozo and not feed.entries:
            discovered = await _autodiscover_feed(url)
            if discovered:
                discovered_body = await _load_feed_bytes(discovered)
                if discovered_body is None:
                    return []
                feed = feedparser.parse(discovered_body)

        items: list[RawContentItem] = []
        for entry in feed.entries:
            link = getattr(entry, "link", None)
            title = getattr(entry, "title", "Untitled")
            if not link:
                continue
            text = _extract_text(entry)
            word_count = _count_words(text) if text else None
            items.append(
                RawContentItem(
                    url=link,
                    title=title,
                    author=getattr(entry, "author", None),
                    published_at=_parse_date(entry),
                    full_text=text or None,
                    word_count=word_count,
                    source_feed_url=url,
                )
            )
        return items
    except Exception as e:
        logger.error(f"Failed to parse feed {url}: {e}")
        return []
