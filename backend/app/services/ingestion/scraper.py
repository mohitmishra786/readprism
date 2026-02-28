from __future__ import annotations

import asyncio
import random
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.config import get_settings
from app.services.ingestion.rss_parser import RawContentItem
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Exponential-backoff retry config
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY = 1.0   # seconds
_RETRY_MAX_DELAY = 30.0   # seconds

_USER_AGENTS = [
    "Mozilla/5.0 (compatible; ReadPrism/1.0; +https://readprism.app/bot)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


async def _check_robots(url: str) -> bool:
    """Returns True if scraping is allowed per robots.txt."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(robots_url)
            rp = RobotFileParser()
            rp.set_url(robots_url)
            rp.parse(resp.text.splitlines())
            return rp.can_fetch("*", url)
    except Exception:
        return True  # if robots.txt unavailable, assume allowed


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


async def _fetch_with_retry(url: str) -> Optional[str]:
    """
    Attempt a lightweight httpx GET with exponential-backoff retry before
    falling back to the Playwright/Browserless path.
    Returns the response HTML or None on all failures.
    """
    user_agent = random.choice(_USER_AGENTS)
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(
                timeout=20,
                follow_redirects=True,
                headers=headers,
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.text
                if resp.status_code in (403, 429, 503):
                    # Likely bot-protected — don't retry with httpx, go straight to Playwright
                    logger.debug(f"HTTP {resp.status_code} on {url} — will use Playwright")
                    return None
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.debug(f"httpx attempt {attempt}/{_RETRY_MAX_ATTEMPTS} failed for {url}: {e}")

        if attempt < _RETRY_MAX_ATTEMPTS:
            delay = min(_RETRY_MAX_DELAY, _RETRY_BASE_DELAY * (2 ** (attempt - 1)))
            await asyncio.sleep(delay + random.uniform(0, 1))

    return None


async def _fetch_with_playwright(url: str) -> tuple[Optional[str], Optional[str]]:
    """Use the headless Chrome instance (Browserless) for JS-rendered pages.
    Returns (html_content, page_title)."""
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


async def scrape_page(url: str) -> Optional[RawContentItem]:
    allowed = await _check_robots(url)
    if not allowed:
        logger.warning(f"Robots.txt disallows scraping: {url}")
        return None

    title: Optional[str] = None
    html_content: Optional[str] = None

    # 1. Fast path: plain httpx GET with retry
    html_content = await _fetch_with_retry(url)

    if html_content:
        # Extract title from <title> tag
        import re
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html_content, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else None

    # 2. Fallback: Playwright for JS-heavy pages
    if not html_content:
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
    reading_time = max(1, round(word_count / 238))

    return RawContentItem(
        url=url,
        title=title,
        full_text=full_text or None,
        word_count=word_count,
    )
