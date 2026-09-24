from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.services.ingestion.rss_parser import fetch_feed, parse_feed

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
async def test_parse_feed_autodiscovers_an_html_page():
    html = b"""<!DOCTYPE html><html><head>
    <link rel="alternate" type="application/rss+xml" href="https://example.com/feed.xml"/>
    </head><body>not a feed</body></html>"""
    seen: list[str] = []

    async def fake_fetch(url: str, **kwargs):
        seen.append(url)
        if url.endswith("/feed.xml"):
            return httpx.Response(200, content=SAMPLE_RSS.encode())
        return httpx.Response(200, content=html)

    with (
        patch("app.services.ingestion.rss_parser.validate_public_url", lambda url, **k: None),
        patch("app.services.ingestion.rss_parser.safe_fetch", fake_fetch),
    ):
        items = await parse_feed("https://example.com/")

    assert seen[0] == "https://example.com/"
    assert "https://example.com/feed.xml" in seen
    assert len(items) == 2


@pytest.mark.asyncio
async def test_second_fetch_of_unchanged_feed_is_304_and_skips_parse():
    """A local mock server. The second request sends the stored validators and
    the parser is not called when the server answers 304."""
    import feedparser

    calls = {"n": 0}

    async def fake_fetch(url: str, **kwargs):
        calls["n"] += 1
        headers = kwargs.get("headers") or {}
        assert headers.get("User-Agent", "").startswith("ReadPrism/1.0")
        assert "br" in headers.get("Accept-Encoding", "")
        if headers.get("If-None-Match") == '"v1"' and headers.get("If-Modified-Since"):
            return httpx.Response(304, headers={"ETag": '"v1"'})
        return httpx.Response(
            200,
            headers={"ETag": '"v1"', "Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT"},
            content=SAMPLE_RSS.encode(),
        )

    real_parse = feedparser.parse
    parsed = {"n": 0}

    def counting_parse(body):
        parsed["n"] += 1
        return real_parse(body)

    with (
        patch("app.services.ingestion.rss_parser.validate_public_url", lambda url, **k: None),
        patch("app.services.ingestion.rss_parser.safe_fetch", fake_fetch),
        patch("app.services.ingestion.rss_parser.feedparser.parse", counting_parse),
    ):
        first = await fetch_feed("https://example.com/feed")
        second = await fetch_feed(
            "https://example.com/feed",
            etag=first.etag,
            last_modified=first.last_modified,
        )

    assert len(first.items) == 2
    assert first.not_modified is False
    assert first.etag == '"v1"'
    assert second.not_modified is True
    assert second.items == []
    assert parsed["n"] == 1
    assert calls["n"] == 2


def test_podcast_transcript_url_is_kept():
    import feedparser

    from app.services.ingestion.rss_parser import _items_from_feed

    xml = """<?xml version="1.0"?>
    <rss version="2.0" xmlns:podcast="https://podcastindex.org/namespace/1.0">
      <channel><item>
        <title>Episode</title>
        <link>https://example.com/ep</link>
        <podcast:transcript url="https://example.com/ep.vtt" type="text/vtt"/>
      </item></channel>
    </rss>"""
    items = _items_from_feed(feedparser.parse(xml), "https://example.com/feed")
    assert items[0].transcript_url == "https://example.com/ep.vtt"


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
