"""Saved-item imports. Each row is origin=import and a positive save signal.

Fixtures cover Feedly/Inoreader starred outlines, the CSV shapes used by
Instapaper, Raindrop and Readwise, a generic url/title/tags CSV, and the
Pocket HTML export (Pocket closed in July 2025; users hold ril_export.html).
No third-party export files are committed.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from io import StringIO

from app.services.ingestion.opml_io import OpmlFeed, parse_opml


@dataclass
class ImportedItem:
    url: str
    title: str
    origin: str = "import"
    saved: bool = True
    note: str | None = None
    tags: list[str] = field(default_factory=list)


CSV_KINDS = ("instapaper", "raindrop", "readwise", "csv")


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
    if kind == "csv":
        return [_generic_row(row) for row in rows]
    raise ValueError(f"unknown import format {kind}")


def detect_csv_kind(text: str) -> str:
    """Pick the CSV shape from its header row (#150)."""
    header = {h.strip().lower() for h in next(csv.reader(StringIO(text)), [])}
    if {"url", "title", "selection"} <= header:
        return "instapaper"
    if {"url", "title", "highlight"} <= header:
        return "readwise"
    if {"url", "title", "excerpt"} <= header:
        return "raindrop"
    return "csv"


def _generic_row(row: dict[str, str | None]) -> ImportedItem:
    """Any CSV with a url column; title and tags (comma/semicolon/pipe) optional."""
    lowered = {(k or "").strip().lower(): (v or "") for k, v in row.items()}
    url = (lowered.get("url") or lowered.get("link") or "").strip()
    title = (lowered.get("title") or url).strip()
    raw_tags = lowered.get("tags") or lowered.get("tag") or ""
    tags = [t.strip() for t in raw_tags.replace(";", ",").replace("|", ",").split(",") if t.strip()]
    return ImportedItem(url=url, title=title, tags=tags)


def import_pocket_html(text: str) -> list[ImportedItem]:
    """Pocket's ril_export.html: <a href time_added tags="a,b">title</a> per item."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(text, "html.parser")
    items: list[ImportedItem] = []
    for link in soup.find_all("a"):
        href = link.get("href")
        url = (href if isinstance(href, str) else "").strip()
        raw_tags = link.get("tags")
        tags_text = raw_tags if isinstance(raw_tags, str) else ""
        tags = [t.strip() for t in tags_text.split(",") if t.strip()]
        items.append(ImportedItem(url=url, title=link.get_text(strip=True) or url, tags=tags))
    return items


def _row(row: dict[str, str | None], url_key: str, title_key: str, note_key: str) -> ImportedItem:
    url = (row.get(url_key) or "").strip()
    title = (row.get(title_key) or url).strip()
    note = (row.get(note_key) or "").strip() or None
    return ImportedItem(url=url, title=title, note=note)


def _starred(feed: OpmlFeed) -> bool:
    tags = {tag.lower() for tag in feed.tags}
    title = feed.title.lower()
    return "starred" in tags or "saved" in tags or "star" in title
