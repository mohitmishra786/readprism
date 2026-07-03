"""Tests for the ingestion dispatcher.

Focuses on the URL-dedup logic (the unit-testable surface). The RSS parsing
and scraping entry points are mocked so no network or DB is required.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ingestion.dispatcher import dispatch_source
from app.services.ingestion.rss_parser import RawContentItem


def _make_source(source_type="rss", feed_url=None, url="https://example.com"):
    source = MagicMock()
    source.id = uuid.uuid4()
    source.user_id = uuid.uuid4()
    source.source_type = source_type
    source.feed_url = feed_url
    source.url = url
    return source


@pytest.mark.asyncio
async def test_dispatch_filters_already_ingested_urls():
    """Items whose URL already exists in the DB are dropped from the result."""
    source = _make_source(feed_url="https://example.com/feed")

    raw_items = [
        RawContentItem(url="https://example.com/a", title="A"),
        RawContentItem(url="https://example.com/b", title="B"),
        RawContentItem(url="https://example.com/c", title="C"),
    ]

    session = AsyncMock()
    # Existing-URL query returns "B" as already ingested.
    existing_result = MagicMock()
    existing_result.fetchall.return_value = [("https://example.com/b",)]
    session.execute = AsyncMock(return_value=existing_result)

    with patch(
        "app.services.ingestion.dispatcher.parse_feed",
        AsyncMock(return_value=raw_items),
    ):
        new_items = await dispatch_source(source, session)

    urls = {item.url for item in new_items}
    assert "https://example.com/a" in urls
    assert "https://example.com/c" in urls
    assert "https://example.com/b" not in urls  # deduped


@pytest.mark.asyncio
async def test_dispatch_returns_empty_when_parse_returns_nothing():
    """If parse_feed returns no items, dispatch returns an empty list without DB work."""
    source = _make_source(feed_url="https://example.com/feed")
    session = AsyncMock()

    with patch(
        "app.services.ingestion.dispatcher.parse_feed",
        AsyncMock(return_value=[]),
    ):
        new_items = await dispatch_source(source, session)

    assert new_items == []


@pytest.mark.asyncio
async def test_dispatch_scraped_source_uses_scraper():
    """A scraped source routes through scrape_page, not parse_feed."""
    source = _make_source(source_type="scraped", url="https://site.com/post")
    session = AsyncMock()

    scraped = RawContentItem(url="https://site.com/post", title="Scraped")
    existing_result = MagicMock()
    existing_result.fetchall.return_value = []
    session.execute = AsyncMock(return_value=existing_result)

    with patch(
        "app.services.ingestion.dispatcher.scrape_page",
        AsyncMock(return_value=scraped),
    ) as mock_scrape, patch(
        "app.services.ingestion.dispatcher.parse_feed",
        AsyncMock(),
    ) as mock_parse:
        new_items = await dispatch_source(source, session)

    mock_scrape.assert_awaited_once()
    mock_parse.assert_not_awaited()
    assert len(new_items) == 1
    assert new_items[0].title == "Scraped"
