from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

import feedparser

from app.utils.logging import get_logger, sanitize_log
from app.utils.sanitize import sanitize_stored_html
from app.utils.ssrf import UnsafeURLError, safe_fetch, validate_public_url
from app.utils.xml_safety import UnsafeXMLError, assert_xml_safe

# Honest identity plus compression. httpx decodes gzip/deflate always, and
# brotli when the brotli package is installed.
_FEED_UA = "ReadPrism/1.0 (+https://readprism.app/bot)"
_FEED_HEADERS = {
    "User-Agent": _FEED_UA,
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}
_FEED_MAX_BYTES = 2_000_000

logger = get_logger(__name__)


@dataclass
class FeedFetchResult:
    """One conditional fetch. `not_modified` means HTTP 304: do not parse or ingest."""

    items: list[RawContentItem]
    not_modified: bool = False
    etag: str | None = None
    last_modified: str | None = None
    status_code: int | None = None


@dataclass
class _HttpFeed:
    status: int
    body: bytes | None
    etag: str | None
    last_modified: str | None


def _conditional_headers(etag: str | None, last_modified: str | None) -> dict[str, str]:
    headers = dict(_FEED_HEADERS)
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


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


def _validators_from(resp) -> tuple[str | None, str | None]:
    etag = resp.headers.get("etag")
    last_modified = resp.headers.get("last-modified")
    return (etag.strip() if etag else None, last_modified.strip() if last_modified else None)


async def _load_feed_bytes(
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
) -> _HttpFeed | None:
    """Fetch a feed through safe_fetch. feedparser must not fetch the URL itself.

    A 304 is returned as status 304 with no body. Callers must not parse it.
    """
    try:
        validate_public_url(url)
    except UnsafeURLError as e:
        logger.warning("Blocked feed fetch for unsafe URL %s: %s", sanitize_log(url), e)
        return None
    try:
        resp = await safe_fetch(
            url,
            headers=_conditional_headers(etag, last_modified),
            timeout=20,
            max_bytes=_FEED_MAX_BYTES,
        )
    except UnsafeURLError as e:
        logger.warning("Blocked feed fetch for %s: %s", sanitize_log(url), e)
        return None
    except Exception as e:
        logger.error("Failed to fetch feed %s: %s", sanitize_log(url), e)
        return None
    response_etag, response_modified = _validators_from(resp)
    if resp.status_code == 304:
        return _HttpFeed(304, None, response_etag or etag, response_modified or last_modified)
    if resp.status_code >= 400:
        logger.warning("Feed %s returned HTTP %s", sanitize_log(url), resp.status_code)
        return _HttpFeed(resp.status_code, None, response_etag, response_modified)
    try:
        body = assert_xml_safe(resp.content, max_bytes=_FEED_MAX_BYTES)
    except UnsafeXMLError as e:
        logger.warning("Rejected unsafe feed XML from %s: %s", sanitize_log(url), e)
        return None
    return _HttpFeed(resp.status_code, body, response_etag, response_modified)


def _items_from_feed(feed, source_url: str) -> list[RawContentItem]:
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
                source_feed_url=source_url,
            )
        )
    return items


async def fetch_feed(
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
) -> FeedFetchResult:
    """Fetch and parse a feed. A 304 returns no items and does not parse."""
    try:
        primary = await _load_feed_bytes(url, etag=etag, last_modified=last_modified)
        if primary is not None and primary.status == 304:
            return FeedFetchResult(
                items=[],
                not_modified=True,
                etag=primary.etag,
                last_modified=primary.last_modified,
                status_code=304,
            )
        if (
            primary is not None
            and primary.status in {410, 429}
            or (primary is not None and primary.status >= 500)
        ):
            return FeedFetchResult(
                items=[],
                etag=primary.etag,
                last_modified=primary.last_modified,
                status_code=primary.status,
            )
        feed = feedparser.parse(primary.body) if primary and primary.body else None
        # A site homepage is not a feed. A 304 must not reach this branch.
        if feed is None or not feed.entries:
            discovered = await _autodiscover_feed(url)
            if discovered and discovered != url:
                secondary = await _load_feed_bytes(discovered)
                if secondary and secondary.status == 304:
                    return FeedFetchResult(
                        items=[],
                        not_modified=True,
                        etag=secondary.etag,
                        last_modified=secondary.last_modified,
                    )
                if secondary and secondary.body:
                    feed = feedparser.parse(secondary.body)
                    if feed is not None:
                        return FeedFetchResult(
                            items=_items_from_feed(feed, discovered),
                            etag=secondary.etag,
                            last_modified=secondary.last_modified,
                        )
        if feed is None:
            return FeedFetchResult(items=[], etag=primary.etag if primary else None)
        return FeedFetchResult(
            items=_items_from_feed(feed, url),
            etag=primary.etag if primary else None,
            last_modified=primary.last_modified if primary else None,
        )
    except Exception as e:
        logger.error(f"Failed to parse feed {url}: {e}")
        return FeedFetchResult(items=[])


async def parse_feed(url: str) -> list[RawContentItem]:
    return (await fetch_feed(url)).items
