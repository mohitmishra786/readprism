from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.services.ingestion.rss_parser import parse_feed

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <item>
      <title>Article One</title>
      <link>https://example.com/article-1</link>
      <description>Summary of article one.</description>
      <pubDate>Mon, 01 Jan 2024 10:00:00 +0000</pubDate>
      <author>Test Author</author>
    </item>
    <item>
      <title>Article Two</title>
      <link>https://example.com/article-2</link>
      <description>Summary of article two.</description>
    </item>
  </channel>
</rss>"""


@pytest.mark.asyncio
async def test_parse_feed_extracts_items():
    """parse_feed reads bytes from safe_fetch and never asks feedparser to fetch."""

    async def fake_fetch(url: str, **kwargs):
        assert url == "https://example.com/feed"
        return httpx.Response(200, content=SAMPLE_RSS.encode())

    with (
        patch("app.services.ingestion.rss_parser.validate_public_url", lambda url, **k: None),
        patch("app.services.ingestion.rss_parser.safe_fetch", fake_fetch),
    ):
        items = await parse_feed("https://example.com/feed")

    assert len(items) == 2
    assert items[0].url == "https://example.com/article-1"
    assert items[0].title == "Article One"
    assert items[0].author == "Test Author"


@pytest.mark.asyncio
async def test_parse_feed_returns_empty_on_error():
    """parse_feed should return empty list on failure without raising."""

    async def fake_fetch(url: str, **kwargs):
        raise RuntimeError("Connection refused")

    with (
        patch("app.services.ingestion.rss_parser.validate_public_url", lambda url, **k: None),
        patch("app.services.ingestion.rss_parser.safe_fetch", fake_fetch),
    ):
        items = await parse_feed("https://bad-url.invalid/feed")
    assert items == []


@pytest.mark.asyncio
async def test_parse_feed_rejects_entity_expansion():
    bomb = b"""<?xml version="1.0"?>
    <!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;">]>
    <rss version="2.0"><channel><item><title>&lol2;</title><link>https://e.com/a</link></item></channel></rss>"""

    async def fake_fetch(url: str, **kwargs):
        return httpx.Response(200, content=bomb)

    with (
        patch("app.services.ingestion.rss_parser.validate_public_url", lambda url, **k: None),
        patch("app.services.ingestion.rss_parser.safe_fetch", fake_fetch),
    ):
        assert await parse_feed("https://example.com/feed") == []
