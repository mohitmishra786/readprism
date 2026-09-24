"""OPML import and export.

Nested folders become source tags. Duplicate feed URLs for the same user are
skipped. A file larger than ``QUEUE_AFTER`` outlines is marked for a background
job; the same function runs either way and reports progress.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

import listparser

QUEUE_AFTER = 200


@dataclass
class OpmlFeed:
    url: str
    title: str
    tags: list[str] = field(default_factory=list)


@dataclass
class OpmlImport:
    feeds: list[OpmlFeed]
    queued: bool
    created: int = 0
    skipped: int = 0
    progress: float = 1.0


def parse_opml(text: str) -> list[OpmlFeed]:
    parsed = listparser.parse(text)
    feeds: list[OpmlFeed] = []
    seen: set[str] = set()
    for feed in parsed.feeds:
        url = (feed.url or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        tags = [str(tag) for tag in (feed.tags or []) if tag]
        feeds.append(OpmlFeed(url=url, title=(feed.title or url).strip(), tags=tags))
    return feeds


def should_queue(count: int) -> bool:
    return count > QUEUE_AFTER


def plan_import(
    text: str,
    existing_urls: set[str],
    progress: Callable[[int, int], None] | None = None,
) -> OpmlImport:
    feeds = parse_opml(text)
    queued = should_queue(len(feeds))
    created: list[OpmlFeed] = []
    skipped = 0
    total = max(len(feeds), 1)
    for index, feed in enumerate(feeds, start=1):
        if feed.url in existing_urls:
            skipped += 1
        else:
            created.append(feed)
            existing_urls.add(feed.url)
        if progress and index % 100 == 0:
            progress(index, total)
    if progress:
        progress(total, total)
    return OpmlImport(
        feeds=created,
        queued=queued,
        created=len(created),
        skipped=skipped,
        progress=1.0,
    )


def export_opml(feeds: list[OpmlFeed], title: str = "ReadPrism") -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="2.0">',
        "<head>",
        f"<title>{escape(title)}</title>",
        "</head>",
        "<body>",
    ]
    folders: dict[str, list[OpmlFeed]] = {}
    loose: list[OpmlFeed] = []
    for feed in feeds:
        if feed.tags:
            folders.setdefault(feed.tags[0], []).append(feed)
        else:
            loose.append(feed)
    for folder, grouped in folders.items():
        lines.append(f'<outline text="{escape(folder)}" title="{escape(folder)}">')
        for feed in grouped:
            lines.append(_outline(feed))
        lines.append("</outline>")
    for feed in loose:
        lines.append(_outline(feed))
    lines.append("</body></opml>")
    return "\n".join(lines)


def _outline(feed: OpmlFeed) -> str:
    return (
        f'<outline type="rss" text="{escape(feed.title)}" title="{escape(feed.title)}" '
        f'xmlUrl="{escape(feed.url)}" htmlUrl="{escape(feed.url)}"/>'
    )
