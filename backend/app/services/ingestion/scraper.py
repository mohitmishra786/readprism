from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from playwright.async_api import async_playwright

from app.config import get_settings
from app.services.ingestion.rss_parser import RawContentItem
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def _check_robots(url: str) -> bool:
    """Returns True if scraping is allowed."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(robots_url)
            rp = RobotFileParser()
            rp.set_url(robots_url)
            # parse() accepts an iterable of lines — correct stdlib API
            rp.parse(resp.text.splitlines())
            return rp.can_fetch("*", url)
    except Exception:
        return True  # if robots.txt unavailable, assume allowed


def _extract_main_content(html_content: str) -> str:
    """Extract readable text from HTML using basic heuristics."""
    from html.parser import HTMLParser

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.text_parts = []
            self.skip_tags = {"script", "style", "nav", "footer", "header", "aside", "noscript"}
            self.current_skip = 0

        def handle_starttag(self, tag, attrs):
            if tag in self.skip_tags:
                self.current_skip += 1

        def handle_endtag(self, tag):
            if tag in self.skip_tags and self.current_skip > 0:
                self.current_skip -= 1

        def handle_data(self, data):
            if self.current_skip == 0:
                stripped = data.strip()
                if stripped:
                    self.text_parts.append(stripped)

    extractor = TextExtractor()
    extractor.feed(html_content)
    return " ".join(extractor.text_parts)


async def scrape_page(url: str) -> Optional[RawContentItem]:
    allowed = await _check_robots(url)
    if not allowed:
        logger.warning(f"Robots.txt disallows scraping: {url}")
        return None

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(settings.browserless_url)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)
            title = await page.title()

            # Try article tag first
            content_html = ""
            for selector in ["article", "main", "[role=main]", ".content", "#content", "body"]:
                try:
                    el = await page.query_selector(selector)
                    if el:
                        content_html = await el.inner_html()
                        break
                except Exception:
                    continue

            await browser.close()

        title = title or "Untitled"
        full_text = _extract_main_content(content_html)
        word_count = len(full_text.split()) if full_text else 0
        reading_time = max(1, round(word_count / 238))

        return RawContentItem(
            url=url,
            title=title,
            full_text=full_text or None,
            word_count=word_count,
        )
    except Exception as e:
        logger.error(f"Failed to scrape {url}: {e}")
        return None
