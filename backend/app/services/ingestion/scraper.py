from __future__ import annotations

import asyncio
import random
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.config import get_settings
from app.services.ingestion.rss_parser import RawContentItem
from app.utils.logging import get_logger
from app.utils.ssrf import UnsafeURLError, safe_get, validate_public_url

logger = get_logger(__name__)
settings = get_settings()

# Exponential-backoff retry config
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY = 1.0  # seconds
_RETRY_MAX_DELAY = 30.0  # seconds

_USER_AGENTS = [
    "Mozilla/5.0 (compatible; ReadPrism/1.0; +https://readprism.app/bot)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


async def _fetch_robots_text(robots_url: str) -> tuple[str, str]:
    """Fetch robots.txt (cached per host). Returns (status, text) where status is
    'ok' (served), 'absent' (clean 404/410), or 'error' (unreachable/5xx)."""
    from app.utils.cache import cache_get, cache_set

    cache_key = f"robots:{robots_url}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached.get("status", "error"), cached.get("text", "")

    status, text = "error", ""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await safe_get(robots_url, client=client)
            if resp.status_code == 200:
                status, text = "ok", resp.text
            elif resp.status_code in (404, 410):
                status = "absent"  # no robots.txt served => allowed by convention
    except Exception as e:
        logger.debug(f"robots.txt fetch failed for {robots_url}: {e}")

    # Cache errors too (short-circuits repeated failing fetches within the TTL).
    await cache_set(
        cache_key, {"status": status, "text": text}, ttl_seconds=settings.robots_cache_ttl_seconds
    )
    return status, text


async def _check_robots(url: str) -> bool:
    """Returns True if scraping is allowed per robots.txt.

    A served robots.txt is honored; a clean 404/410 (none served) is allowed by
    convention; a fetch error fails **closed** by default (audit 08-6), which
    `robots_fail_open` can override.
    """
    try:
        validate_public_url(url)
    except UnsafeURLError as e:
        logger.warning(f"Blocked robots fetch for unsafe URL {url}: {e}")
        return False

    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    status, text = await _fetch_robots_text(robots_url)

    if status == "absent":
        return True
    if status == "error":
        return settings.robots_fail_open
    rp = RobotFileParser()
    rp.set_url(robots_url)
    rp.parse(text.splitlines())
    return rp.can_fetch("*", url)


def _extract_with_trafilatura(html_content: str, url: str) -> str:
    """
    Use trafilatura for high-quality main-content extraction.
    Falls back to a simple tag-stripping approach if trafilatura returns nothing.
    """
    try:
        import trafilatura

        text = trafilatura.extract(
            html_content,
            url=url,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_recall=True,
        )
        if text and len(text.strip()) > 100:
            return text.strip()
    except Exception as e:
        logger.debug(f"trafilatura extraction failed ({e}), using fallback")

    # Fallback: BeautifulSoup paragraph extraction (better than raw tag-stripping)
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        paragraphs = [p.get_text(separator=" ", strip=True) for p in soup.find_all("p")]
        text = " ".join(p for p in paragraphs if len(p) > 40)
        return text.strip()
    except Exception as e:
        logger.debug(f"BeautifulSoup fallback failed: {e}")
        return ""


async def _fetch_with_retry(url: str) -> tuple[str | None, bool]:
    """
    Attempt a lightweight httpx GET with exponential-backoff retry.
    Returns (html, was_blocked): `was_blocked` is True when the site explicitly
    refused our bot (403/429/503), so the caller can respect the block instead
    of circumventing it (audit 08-2).
    """
    # Honest posture: identify as the ReadPrism bot rather than rotating
    # browser-impersonation User-Agents.
    user_agent = (
        _USER_AGENTS[0] if settings.scraper_identify_as_bot else random.choice(_USER_AGENTS)
    )
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(
                timeout=20,
                headers=headers,
            ) as client:
                # safe_get validates the URL and every redirect hop (SSRF guard).
                resp = await safe_get(url, client=client)
                if resp.status_code == 200:
                    return resp.text, False
                if resp.status_code in (403, 429, 503):
                    logger.debug(f"HTTP {resp.status_code} on {url} — site blocked our bot")
                    return None, True
        except UnsafeURLError as e:
            logger.warning(f"Blocked fetch for unsafe URL {url}: {e}")
            return None, False
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.debug(f"httpx attempt {attempt}/{_RETRY_MAX_ATTEMPTS} failed for {url}: {e}")

        if attempt < _RETRY_MAX_ATTEMPTS:
            delay = min(_RETRY_MAX_DELAY, _RETRY_BASE_DELAY * (2 ** (attempt - 1)))
            await asyncio.sleep(delay + random.uniform(0, 1))

    return None, False


async def _fetch_with_playwright(url: str) -> tuple[str | None, str | None]:
    """Use the headless Chrome instance (Browserless) for JS-rendered pages.
    Returns (html_content, page_title)."""
    try:
        # Browserless renders arbitrary user-supplied URLs; validate before we
        # hand the URL to the headless browser (SSRF guard, audit 06-2).
        validate_public_url(url)
    except UnsafeURLError as e:
        logger.warning(f"Blocked Playwright fetch for unsafe URL {url}: {e}")
        return None, None

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(settings.browserless_url)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Extract HTML from most-specific content container first
            content_html = ""
            for selector in ["article", "main", "[role=main]", ".content", "#content", "body"]:
                try:
                    el = await page.query_selector(selector)
                    if el:
                        content_html = await el.inner_html()
                        break
                except Exception:
                    continue

            page_title = await page.title()
            await browser.close()
            return content_html or None, page_title
    except Exception as e:
        logger.error(f"Playwright fetch failed for {url}: {e}")
        return None, None


async def scrape_page(url: str) -> RawContentItem | None:
    allowed = await _check_robots(url)
    if not allowed:
        logger.warning(f"Robots.txt disallows scraping: {url}")
        return None

    title: str | None = None
    html_content: str | None = None

    # 1. Fast path: plain httpx GET with retry
    html_content, was_blocked = await _fetch_with_retry(url)

    if html_content:
        # Extract title from <title> tag
        import re

        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html_content, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else None

    # 2. Fallback: Playwright for JS-heavy pages. If the site *explicitly blocked*
    #    our identified bot, respect that rather than circumventing it with a
    #    headless browser (audit 08-2); still fall back for genuine JS rendering.
    if not html_content:
        if was_blocked and settings.scraper_respect_blocks:
            logger.info(f"Respecting {url} block — not escalating to headless browser")
            return None
        result = await _fetch_with_playwright(url)
        if isinstance(result, tuple):
            html_content, title = result
        else:
            html_content = result

    if not html_content:
        logger.warning(f"All fetch strategies failed for {url}")
        return None

    title = title or "Untitled"
    full_text = _extract_with_trafilatura(html_content, url)
    word_count = len(full_text.split()) if full_text else 0

    return RawContentItem(
        url=url,
        title=title,
        full_text=full_text or None,
        word_count=word_count,
    )
