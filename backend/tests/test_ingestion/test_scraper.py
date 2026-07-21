"""Tests for the web scraper.

Internal fetch + robots helpers are monkeypatched so no real network calls are
made. Covers:
- trafilatura extraction from a realistic article HTML body
- robots.txt enforcement (disallowed → None)
- graceful None when all fetch strategies fail
"""

from __future__ import annotations

import pytest

from app.services.ingestion.scraper import _extract_with_trafilatura, scrape_page

# A small but realistic article body. trafilatura should extract the prose
# paragraphs and ignore the nav/footer noise.
ARTICLE_HTML = """
<html><head><title>Real Article</title></head>
<body>
  <nav>Home About Contact</nav>
  <article>
    <h1>Real Article</h1>
    <p>Working memory is the cognitive system that holds and manipulates
       information over short periods. It is distinct from long-term memory
       because it is limited in capacity and duration.</p>
    <p>The classic model proposes separate components: a central executive
       that controls attention, and modality-specific storage buffers that
       maintain representations through rehearsal and active maintenance.</p>
    <p>Empirical studies consistently show a capacity limit of roughly four
       items, challenging older estimates of the so-called magical number
       seven plus or minus two that dominated the early literature.</p>
  </article>
  <footer>Copyright notice. Cookie banner. Newsletter signup.</footer>
</body></html>
"""


def test_trafilatura_extracts_main_content():
    """The extractor should pull the article prose and exclude nav/footer."""
    text = _extract_with_trafilatura(ARTICLE_HTML, "https://example.com/post")
    assert text, "Expected non-empty extraction"
    assert "working memory" in text.lower()
    assert "newsletter signup" not in text.lower()
    assert "cookie banner" not in text.lower()


def test_trafilatura_returns_empty_on_non_content():
    """A page with no meaningful prose yields empty (or near-empty) text."""
    noise = "<html><body><nav>a b c</nav><footer>x y z</footer></body></html>"
    # We don't assert emptiness strictly (the fallback may pick up short bits),
    # but it must not raise.
    text = _extract_with_trafilatura(noise, "https://example.com")
    assert isinstance(text, str)


@pytest.mark.asyncio
async def test_scrape_page_returns_none_when_disallowed_by_robots(monkeypatch):
    """If robots.txt disallows the path, scrape_page returns None without fetching."""

    # Force the robots check to forbid the URL.
    async def _deny(_url):
        return False

    monkeypatch.setattr("app.services.ingestion.scraper._check_robots", _deny)
    result = await scrape_page("https://example.com/secret")
    assert result is None


@pytest.mark.asyncio
async def test_scrape_page_extracts_article_on_success(monkeypatch):
    """A successful 200 fetch with article HTML returns a RawContentItem.

    We patch the internal fetch + robots helpers directly rather than mocking
    raw httpx, so the test exercises the extraction + RawContentItem assembly
    (the parts that matter) without coupling to the retry/Playwright plumbing.
    """

    async def _allow(_url):
        return True

    async def _fake_fetch(_url):
        return ARTICLE_HTML, False

    monkeypatch.setattr("app.services.ingestion.scraper._check_robots", _allow)
    monkeypatch.setattr("app.services.ingestion.scraper._fetch_with_retry", _fake_fetch)

    result = await scrape_page("https://example.com/post")
    assert result is not None
    assert result.title == "Real Article"
    assert result.url == "https://example.com/post"
    assert result.word_count and result.word_count > 0
    assert "working memory" in (result.full_text or "").lower()


@pytest.mark.asyncio
async def test_scrape_page_returns_none_when_all_fetches_fail(monkeypatch):
    """When both httpx and Playwright fetches fail, scrape_page returns None."""

    async def _allow(_url):
        return True

    async def _fetch_none(_url):
        return None, False

    async def _playwright_none(_url):
        return (None, None)

    monkeypatch.setattr("app.services.ingestion.scraper._check_robots", _allow)
    monkeypatch.setattr("app.services.ingestion.scraper._fetch_with_retry", _fetch_none)
    monkeypatch.setattr("app.services.ingestion.scraper._fetch_with_playwright", _playwright_none)

    result = await scrape_page("https://example.com/nothing")
    assert result is None


@pytest.mark.asyncio
async def test_scrape_page_respects_block_without_browser_fallback(monkeypatch):
    """When the site blocks our bot (403/429), we back off instead of using the
    headless browser to circumvent it (honest posture, audit 08-2)."""
    from app.services.ingestion import scraper

    async def _allow(_url):
        return True

    async def _blocked(_url):
        return None, True

    playwright_called = False

    async def _playwright(_url):
        nonlocal playwright_called
        playwright_called = True
        return ("<html></html>", "T")

    monkeypatch.setattr(scraper, "_check_robots", _allow)
    monkeypatch.setattr(scraper, "_fetch_with_retry", _blocked)
    monkeypatch.setattr(scraper, "_fetch_with_playwright", _playwright)
    monkeypatch.setattr(scraper.settings, "scraper_respect_blocks", True)

    result = await scraper.scrape_page("https://example.com/blocked")
    assert result is None
    assert playwright_called is False  # did not circumvent the block


@pytest.mark.asyncio
async def test_check_robots_allows_when_absent(monkeypatch):
    """A clean 404 (no robots.txt) means scraping is allowed by convention."""
    from app.services.ingestion import scraper

    async def _absent(_url):
        return "absent", ""

    monkeypatch.setattr(scraper, "_fetch_robots_text", _absent)
    assert await scraper._check_robots("https://example.com/post") is True


@pytest.mark.asyncio
async def test_check_robots_fails_closed_on_error(monkeypatch):
    """When robots.txt is unreachable, deny by default (fail closed)."""
    from app.services.ingestion import scraper

    async def _error(_url):
        return "error", ""

    monkeypatch.setattr(scraper, "_fetch_robots_text", _error)
    monkeypatch.setattr(scraper.settings, "robots_fail_open", False)
    assert await scraper._check_robots("https://example.com/post") is False
    # ...unless explicitly configured fail-open.
    monkeypatch.setattr(scraper.settings, "robots_fail_open", True)
    assert await scraper._check_robots("https://example.com/post") is True


@pytest.mark.asyncio
async def test_check_robots_honors_disallow(monkeypatch):
    """A served robots.txt disallow rule is respected."""
    from app.services.ingestion import scraper

    async def _served(_url):
        return "ok", "User-agent: *\nDisallow: /secret"

    monkeypatch.setattr(scraper, "_fetch_robots_text", _served)
    assert await scraper._check_robots("https://example.com/secret/page") is False
    assert await scraper._check_robots("https://example.com/public") is True
