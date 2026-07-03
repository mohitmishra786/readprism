"""Tests for creator identity resolution across platforms.

Covers the platform feed URL builders (Substack/Medium/YouTube/Reddit/podcast)
and the honest-warning paths for closed platforms (Twitter/LinkedIn). HTTP
fetches are mocked so no network is required.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.creator.resolver import (
    PLATFORM_CAPABILITIES,
    _autodiscover_feed_url,
    _detect_platform,
    get_platform_tier,
)


# ---------------------------------------------------------------------------
# Platform detection from URL.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://example.substack.com/p/foo", "substack"),
        ("https://substack.com/@user", "substack"),
        ("https://www.youtube.com/@channel", "youtube"),
        ("https://youtu.be/abc123", "youtube"),
        ("https://twitter.com/elonmusk", "twitter"),
        ("https://x.com/elonmusk", "twitter"),
        ("https://medium.com/@author", "medium"),
        ("https://www.linkedin.com/in/person", "linkedin"),
        ("https://open.spotify.com/show/123", "podcast"),
        ("https://www.reddit.com/r/MachineLearning", "reddit"),
        ("https://old.reddit.com/user/spez", "reddit"),
        ("https://someblog.com/post", "blog"),
    ],
)
def test_detect_platform(url, expected):
    assert _detect_platform(url) == expected


# ---------------------------------------------------------------------------
# Platform capability tiers (honesty layer).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "platform,expected_tier",
    [
        ("substack", "fully_tracked"),
        ("medium", "fully_tracked"),
        ("youtube", "fully_tracked"),
        ("reddit", "fully_tracked"),
        ("blog", "best_effort"),
        ("podcast", "best_effort"),
        ("twitter", "unsupported"),
        ("linkedin", "unsupported"),
    ],
)
def test_platform_tiers(platform, expected_tier):
    assert get_platform_tier(platform) == expected_tier


def test_all_known_platforms_have_capabilities():
    """Every platform we detect must have a tracking_tier and display_label."""
    known = {"substack", "youtube", "twitter", "medium", "linkedin", "podcast", "reddit", "blog"}
    for p in known:
        assert p in PLATFORM_CAPABILITIES, f"{p} missing from PLATFORM_CAPABILITIES"
        caps = PLATFORM_CAPABILITIES[p]
        assert "tracking_tier" in caps
        assert "display_label" in caps


# ---------------------------------------------------------------------------
# Feed URL autodiscovery — the fully_tracked platforms.
# ---------------------------------------------------------------------------
def test_substack_feed_url():
    feed, warning = _autodiscover_feed_url(
        "substack", "https://foo.substack.com/p/post", ""
    )
    assert feed == "https://foo.substack.com/feed"
    assert warning is None


def test_medium_feed_url():
    feed, warning = _autodiscover_feed_url(
        "medium", "https://medium.com/@author/post", ""
    )
    assert feed == "https://medium.com/feed/@author"
    assert warning is None


def test_medium_subdomain_publication_feed_url():
    """A subdomain-hosted Medium blog (author.medium.com) resolves a feed too."""
    feed, warning = _autodiscover_feed_url(
        "medium", "https://johndoe.medium.com/", ""
    )
    assert feed == "https://johndoe.medium.com/feed"
    assert warning is None


def test_youtube_feed_url_from_channel_id_in_html():
    html = '<meta content="UC_x5XG1OV2P6uZZ5FSM9Ttw" itemprop="channelId">'
    feed, warning = _autodiscover_feed_url(
        "youtube", "https://www.youtube.com/@Google", html
    )
    assert feed == "https://www.youtube.com/feeds/videos.xml?channel_id=UC_x5XG1OV2P6uZZ5FSM9Ttw"
    assert warning is None


def test_youtube_no_channel_id_returns_warning():
    feed, warning = _autodiscover_feed_url("youtube", "https://www.youtube.com/@x", "")
    assert feed is None
    assert warning is not None  # honest warning about missing channel id


def test_reddit_subreddit_feed_url():
    """Appending .rss to a subreddit URL yields a valid feed."""
    feed, warning = _autodiscover_feed_url(
        "reddit", "https://www.reddit.com/r/MachineLearning", ""
    )
    assert feed == "https://www.reddit.com/r/MachineLearning/.rss"
    assert warning is None


def test_reddit_user_feed_url():
    feed, warning = _autodiscover_feed_url(
        "reddit", "https://www.reddit.com/user/spez", ""
    )
    assert feed == "https://www.reddit.com/user/spez/.rss"
    assert warning is None


def test_reddit_strips_query_and_fragment():
    feed, _ = _autodiscover_feed_url(
        "reddit", "https://www.reddit.com/r/MachineLearning/?sort=new#main", ""
    )
    assert feed == "https://www.reddit.com/r/MachineLearning/.rss"


# ---------------------------------------------------------------------------
# Closed platforms — honest warnings, no feed.
# ---------------------------------------------------------------------------
def test_twitter_returns_none_with_warning():
    feed, warning = _autodiscover_feed_url("twitter", "https://twitter.com/x", "")
    assert feed is None
    assert warning is not None
    assert "no public RSS feed" in warning.lower() or "cannot" in warning.lower()


def test_linkedin_returns_none_with_warning():
    feed, warning = _autodiscover_feed_url("linkedin", "https://linkedin.com/in/x", "")
    assert feed is None
    assert warning is not None


# ---------------------------------------------------------------------------
# Generic blog RSS autodiscovery from <link> tags.
# ---------------------------------------------------------------------------
def test_blog_autodiscovery_absolute_href():
    html = (
        '<head><link rel="alternate" type="application/rss+xml" '
        'href="https://blog.example.com/feed.xml" /></head>'
    )
    feed, warning = _autodiscover_feed_url("blog", "https://blog.example.com/post", html)
    assert feed == "https://blog.example.com/feed.xml"
    assert warning is None


def test_blog_autodiscovery_relative_href_resolved():
    html = (
        '<head><link rel="alternate" type="application/rss+xml" href="/rss" /></head>'
    )
    feed, _ = _autodiscover_feed_url("blog", "https://blog.example.com/post", html)
    assert feed == "https://blog.example.com/rss"


def test_blog_no_feed_link_returns_none():
    feed, warning = _autodiscover_feed_url("blog", "https://blog.example.com/post", "<html></html>")
    assert feed is None
    assert warning is not None  # limitation message


# ---------------------------------------------------------------------------
# Podcast iTunes lookup — mocked.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_podcast_lookup_returns_itunes_feed():
    from app.services.creator.resolver import _lookup_podcast_feed

    fake_response = MagicMock()
    fake_response.json.return_value = {
        "results": [{"feedUrl": "https://podcasts.example.com/show.rss"}]
    }
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=fake_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        feed = await _lookup_podcast_feed("My Show")
        assert feed == "https://podcasts.example.com/show.rss"


@pytest.mark.asyncio
async def test_podcast_lookup_no_results_returns_none():
    from app.services.creator.resolver import _lookup_podcast_feed

    fake_response = MagicMock()
    fake_response.json.return_value = {"results": []}
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=fake_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        feed = await _lookup_podcast_feed("Obscure Show")
        assert feed is None


@pytest.mark.asyncio
async def test_podcast_lookup_empty_name_returns_none():
    from app.services.creator.resolver import _lookup_podcast_feed

    assert await _lookup_podcast_feed("") is None
