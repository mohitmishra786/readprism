"""Twenty site shapes. HTML is a short fixture, not a copied page."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.services.ingestion.discover import discover_feed_candidates

FEED = "<rss><channel><title>Feed</title></channel></rss>"


def _link(href: str, type_first: bool = True) -> str:
    if type_first:
        tag = f'<link rel="alternate" type="application/rss+xml" href="{href}"/>'
    else:
        tag = f'<link rel="alternate" href="{href}" type="application/atom+xml"/>'
    return f"<!DOCTYPE html><html><head>{tag}</head><body></body></html>"


CASES = [
    (
        "wordpress",
        "https://blog.example.com/2024/01/hello",
        _link("/feed/"),
        "https://blog.example.com/feed/",
        "link",
    ),
    (
        "wordpress.com",
        "https://name.wordpress.com/",
        _link("https://name.wordpress.com/feed/"),
        "https://name.wordpress.com/feed/",
        "link",
    ),
    (
        "ghost",
        "https://ghost.example.com/post",
        _link("/rss/"),
        "https://ghost.example.com/rss/",
        "link",
    ),
    (
        "ghost-href-first",
        "https://ghost.example.com/",
        _link("/rss/", type_first=False),
        "https://ghost.example.com/rss/",
        "link",
    ),
    (
        "substack",
        "https://name.substack.com/p/hello",
        "",
        "https://name.substack.com/feed",
        "platform",
    ),
    (
        "substack-custom",
        "https://newsletter.example.com/",
        _link("https://newsletter.example.com/feed"),
        "https://newsletter.example.com/feed",
        "link",
    ),
    (
        "blogger",
        "https://name.blogspot.com/2024/01/post.html",
        "",
        "https://name.blogspot.com/feeds/posts/default",
        "platform",
    ),
    (
        "hugo",
        "https://hugo.example.com/posts/one",
        _link("/index.xml"),
        "https://hugo.example.com/index.xml",
        "link",
    ),
    (
        "jekyll",
        "https://jekyll.example.com/2024/01/01/post.html",
        _link("/feed.xml"),
        "https://jekyll.example.com/feed.xml",
        "link",
    ),
    (
        "medium-user",
        "https://medium.com/@octocat/a-post",
        "",
        "https://medium.com/feed/@octocat",
        "platform",
    ),
    (
        "medium-publication",
        "https://medium.com/some-publication",
        "",
        "https://medium.com/feed/some-publication",
        "platform",
    ),
    (
        "medium-subdomain",
        "https://pub.medium.com/story",
        "",
        "https://pub.medium.com/feed",
        "platform",
    ),
    (
        "youtube",
        "https://www.youtube.com/@Google",
        '<html><meta itemprop="channelId" content="UCxxxxxxxxxxxxxxxx"/></html>',
        "https://www.youtube.com/feeds/videos.xml?channel_id=UCxxxxxxxxxxxxxxxx",
        "platform",
    ),
    (
        "reddit",
        "https://www.reddit.com/r/MachineLearning",
        "",
        "https://www.reddit.com/r/MachineLearning/.rss",
        "platform",
    ),
    (
        "reddit-named-top",
        "https://www.reddit.com/r/top",
        "",
        "https://www.reddit.com/r/top/.rss",
        "platform",
    ),
    (
        "mastodon-fosstodon",
        "https://fosstodon.org/@alice",
        "",
        "https://fosstodon.org/@alice.rss",
        "platform",
    ),
    (
        "github",
        "https://github.com/owner/repo",
        "",
        "https://github.com/owner/repo/releases.atom",
        "platform",
    ),
    (
        "arxiv",
        "https://arxiv.org/list/cs.LG/recent",
        "",
        "https://rss.arxiv.org/rss/cs.LG",
        "platform",
    ),
    (
        "hugo-probe",
        "https://docs.example.com/guide",
        "<html><body>no links</body></html>",
        "https://docs.example.com/index.xml",
        "well_known",
    ),
    (
        "jekyll-probe",
        "https://notes.example.com/",
        "<html></html>",
        "https://notes.example.com/atom.xml",
        "well_known",
    ),
    (
        "js-only",
        "https://app.example.com/article",
        '<html><body><div id="root"></div><noscript>enable js</noscript></body></html>',
        "https://app.example.com/article",
        "scrape",
    ),
    (
        "rsshub-x",
        "https://x.com/someuser",
        "<html></html>",
        "https://rsshub.example/twitter/user/someuser",
        "rsshub",
    ),
]


def _probe_factory(kind: str, expected: str):
    async def _fetch(url: str) -> str | None:
        if url.split("#")[0] == expected.split("#")[0]:
            return FEED
        if kind == "hugo-probe" and url.endswith("/index.xml"):
            return FEED
        if kind == "jekyll-probe" and url.endswith("/atom.xml"):
            return FEED
        return None

    return _fetch


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "page", "html", "expected", "method"), CASES)
async def test_fixture_site_resolves(kind, page, html, expected, method, monkeypatch):
    if kind == "rsshub-x":
        monkeypatch.setattr(get_settings(), "rsshub_base_url", "https://rsshub.example")
    else:
        monkeypatch.setattr(get_settings(), "rsshub_base_url", "")
    found = await discover_feed_candidates(page, html=html, fetch=_probe_factory(kind, expected))
    assert found, kind
    assert found[0].url == expected
    assert found[0].method == method
