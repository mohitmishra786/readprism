"""BibTeX and RIS export of saved items, for Zotero and other reference
managers (#250).

Entry types from the URL: an arXiv abstract page becomes a preprint with its
eprint id, a DOI becomes a journal article with the DOI, everything else a
web page. Each entry carries the title, author, publication date, URL, the
date you saved it, the summary as the abstract, and your topics as keywords.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from urllib.parse import urlparse

from app.models.content import ContentItem, UserContentInteraction

_ARXIV = re.compile(
    r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/[0-9]{7})(?:v\d+)?", re.I
)
_DOI = re.compile(r"(10\.\d{4,9}/[^\s?#]+)", re.I)
_BIBTEX_SPECIAL = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "%": r"\%",
    "&": r"\&",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "^": r"\^{}",
    "~": r"\~{}",
}


def kind_of(url: str) -> tuple[str, str | None]:
    """('arxiv', id) | ('doi', doi) | ('web', None)."""
    if m := _ARXIV.search(url or ""):
        return "arxiv", m.group(1)
    host = urlparse(url or "").netloc.lower()
    if (m := _DOI.search(url or "")) and ("doi" in host or "/doi/" in (url or "")):
        return "doi", m.group(1).rstrip(".")
    return "web", None


def _site(url: str) -> str:
    return urlparse(url or "").netloc.lower().removeprefix("www.")


def _bib_escape(value: str) -> str:
    return "".join(_BIBTEX_SPECIAL.get(ch, ch) for ch in value)


def _ascii_word(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]", "", plain)


def _first_author_surname(authors: str | None) -> str:
    """'Ada Lovelace and Alan Turing' -> 'Lovelace'; 'Varga, Ines' -> 'Varga'."""
    first = re.split(r"\s+and\s+|;", authors or "")[0].strip()
    if not first:
        return ""
    surname = first.split(",")[0] if "," in first else first.split()[-1]
    return _ascii_word(surname)


def _cite_key(item: ContentItem, used: set[str]) -> str:
    who = _first_author_surname(item.author) or _ascii_word(_site(item.url).split(".")[0])
    year = str(item.published_at.year) if item.published_at else "nd"
    word = next(
        (_ascii_word(w) for w in (item.title or "").split() if len(_ascii_word(w)) > 3), "item"
    )
    base = f"{who.lower() or 'anon'}{year}{word.lower()}"
    key, n = base, 0
    while key in used:
        n += 1
        key = f"{base}{chr(ord('a') + n - 1)}" if n <= 26 else f"{base}{n}"
    used.add(key)
    return key


def _keywords(item: ContentItem, ix: UserContentInteraction) -> list[str]:
    seen: list[str] = []
    for word in [*(item.topic_clusters or []), *(ix.tags or [])]:
        if word and word not in seen:
            seen.append(str(word))
    return seen


def to_bibtex(rows: list[tuple[ContentItem, UserContentInteraction]]) -> str:
    used: set[str] = set()
    entries = []
    for item, ix in rows:
        kind, ident = kind_of(item.url)
        fields: list[tuple[str, str]] = [("title", f"{{{_bib_escape(item.title or item.url)}}}")]
        if item.author:
            fields.append(("author", _bib_escape(item.author)))
        if item.published_at:
            fields.append(("year", str(item.published_at.year)))
            fields.append(("date", item.published_at.date().isoformat()))
        if kind == "arxiv" and ident:
            entry_type = "misc"
            fields += [("eprint", ident), ("archivePrefix", "arXiv")]
        elif kind == "doi" and ident:
            entry_type = "article"
            fields.append(("doi", _bib_escape(ident)))
        else:
            entry_type = "misc"
            fields.append(("howpublished", _bib_escape(_site(item.url))))
        fields.append(("url", item.url))
        saved = ix.saved_at or ix.created_at
        if isinstance(saved, datetime):
            fields.append(("urldate", saved.date().isoformat()))
        if item.summary_brief:
            fields.append(("abstract", _bib_escape(item.summary_brief)))
        if words := _keywords(item, ix):
            fields.append(("keywords", _bib_escape(", ".join(words))))
        body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields)
        entries.append(f"@{entry_type}{{{_cite_key(item, used)},\n{body}\n}}")
    return "\n\n".join(entries) + ("\n" if entries else "")


def to_ris(rows: list[tuple[ContentItem, UserContentInteraction]]) -> str:
    records = []
    for item, ix in rows:
        kind, ident = kind_of(item.url)
        ty = {"arxiv": "UNPB", "doi": "JOUR"}.get(kind, "ELEC")
        lines = [("TY", ty), ("TI", item.title or item.url)]
        if item.author:
            lines.append(("AU", item.author))
        if item.published_at:
            lines.append(("PY", str(item.published_at.year)))
            lines.append(("DA", item.published_at.strftime("%Y/%m/%d")))
        if kind == "doi" and ident:
            lines.append(("DO", ident))
        if kind == "arxiv" and ident:
            lines.append(("M1", f"arXiv:{ident}"))
        lines.append(("UR", item.url))
        lines.append(("PB", _site(item.url)))
        saved = ix.saved_at or ix.created_at
        if isinstance(saved, datetime):
            lines.append(("Y2", saved.strftime("%Y/%m/%d")))
        if item.summary_brief:
            lines.append(("AB", " ".join(item.summary_brief.split())))
        lines += [("KW", word) for word in _keywords(item, ix)]
        lines.append(("ER", ""))
        records.append(
            "\n".join(f"{tag}  - {' '.join(str(value).split())}".rstrip() for tag, value in lines)
        )
    return "\n\n".join(records) + ("\n" if records else "")
