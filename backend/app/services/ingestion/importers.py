"""Saved-item imports. Each row is origin=import and a positive save signal.

Fixtures cover Feedly/Inoreader starred outlines and the CSV shapes used by
Instapaper, Raindrop, and Readwise. No third-party export files are committed.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO

from app.services.ingestion.opml_io import OpmlFeed, parse_opml


@dataclass
class ImportedItem:
    url: str
    title: str
    origin: str = "import"
    saved: bool = True
    note: str | None = None


def import_opml_starred(text: str) -> list[ImportedItem]:
    """Feedly and Inoreader starred exports are OPML outlines, often tagged starred."""
    items: list[ImportedItem] = []
    for feed in parse_opml(text):
        if not _starred(feed):
            continue
        items.append(ImportedItem(url=feed.url, title=feed.title, note="starred"))
    return items


def import_csv(text: str, kind: str) -> list[ImportedItem]:
    reader = csv.DictReader(StringIO(text))
    rows = list(reader)
    if kind == "instapaper":
        return [_row(row, "URL", "Title", "Selection") for row in rows if row.get("URL")]
    if kind == "raindrop":
        return [_row(row, "url", "title", "excerpt") for row in rows if row.get("url")]
    if kind == "readwise":
        return [_row(row, "URL", "Title", "Highlight") for row in rows if row.get("URL")]
    raise ValueError(f"unknown import format {kind}")


def _row(row: dict[str, str | None], url_key: str, title_key: str, note_key: str) -> ImportedItem:
    url = (row.get(url_key) or "").strip()
    title = (row.get(title_key) or url).strip()
    note = (row.get(note_key) or "").strip() or None
    return ImportedItem(url=url, title=title, note=note)


def _starred(feed: OpmlFeed) -> bool:
    tags = {tag.lower() for tag in feed.tags}
    title = feed.title.lower()
    return "starred" in tags or "saved" in tags or "star" in title
