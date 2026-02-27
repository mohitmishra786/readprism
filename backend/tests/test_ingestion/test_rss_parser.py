from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from app.services.ingestion.rss_parser import parse_feed, RawContentItem

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
    """parse_feed should return correct number of items from RSS fixture."""
    import feedparser
    with patch.object(feedparser, "parse") as mock_parse:
        mock_result = MagicMock()
        mock_result.bozo = False
        entry1 = MagicMock()
        entry1.link = "https://example.com/article-1"
        entry1.title = "Article One"
        entry1.author = "Test Author"
        entry1.published_parsed = (2024, 1, 1, 10, 0, 0, 0, 1, 0)
        entry1.summary = "Summary of article one."
        entry1.content = []
        entry2 = MagicMock()
        entry2.link = "https://example.com/article-2"
        entry2.title = "Article Two"
        entry2.author = None
        entry2.published_parsed = None
        entry2.summary = "Summary of article two."
        entry2.content = []
        mock_result.entries = [entry1, entry2]
        mock_parse.return_value = mock_result

        items = await parse_feed("https://example.com/feed")

    assert len(items) == 2
    assert items[0].url == "https://example.com/article-1"
    assert items[0].title == "Article One"
    assert items[0].author == "Test Author"


@pytest.mark.asyncio
async def test_parse_feed_returns_empty_on_error():
    """parse_feed should return empty list on failure without raising."""
    import feedparser
    with patch.object(feedparser, "parse", side_effect=Exception("Connection refused")):
        items = await parse_feed("https://bad-url.invalid/feed")
    assert items == []
