"""Author, dates, language, reading time, lead image, and a paywall label.

Paywall detection never fetches an alternate URL. It only labels the page.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from bs4 import BeautifulSoup

_LANG = re.compile(r"^[a-z]{2}(?:-[a-z0-9]+)?$", re.IGNORECASE)
_EN_STOPS = {"the", "and", "of", "to", "a", "in", "that", "is", "for", "on"}


@dataclass
class PageMeta:
    author: str | None = None
    published_at: datetime | None = None
    language: str | None = None
    lead_image_url: str | None = None
    paywalled: bool = False
    word_count: int = 0
    reading_time_minutes: int | None = None


def reading_time(word_count: int | None) -> int | None:
    if not word_count or word_count <= 0:
        return None
    return max(1, round(word_count / 200))


def extract_metadata(
    html: str | None,
    *,
    text: str | None = None,
    author: str | None = None,
    published_at: datetime | None = None,
) -> PageMeta:
    soup = BeautifulSoup(html or "", "html.parser")
    linked = _json_ld(soup)
    meta = PageMeta(
        author=author
        or linked.get("author")
        or _meta(soup, "author")
        or _meta(soup, "article:author"),
        published_at=published_at
        or _parse_time(linked.get("date") or _meta(soup, "article:published_time")),
        language=_language(soup, text or ""),
        lead_image_url=linked.get("image") or _meta(soup, "og:image"),
        paywalled=_paywalled(html or "", linked),
        word_count=len((text or "").split()),
    )
    meta.reading_time_minutes = reading_time(meta.word_count)
    return meta


def _meta(soup: BeautifulSoup, name: str) -> str | None:
    tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
    if not tag:
        return None
    content = tag.get("content")
    return str(content).strip() if content else None


def _json_ld(soup: BeautifulSoup) -> dict[str, str]:
    found: dict[str, str] = {}
    for script in soup.find_all("script"):
        kind = (
            " ".join(script.get("type") or []).lower()
            if isinstance(script.get("type"), list)
            else str(script.get("type") or "")
        )
        if "ld+json" not in kind:
            continue
        try:
            payload = json.loads(script.string or "")
        except (TypeError, json.JSONDecodeError):
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            author = node.get("author")
            if isinstance(author, dict) and author.get("name"):
                found.setdefault("author", str(author["name"]))
            elif isinstance(author, str):
                found.setdefault("author", author)
            if node.get("datePublished"):
                found.setdefault("date", str(node["datePublished"]))
            image = node.get("image")
            if isinstance(image, str):
                found.setdefault("image", image)
            elif isinstance(image, dict) and image.get("url"):
                found.setdefault("image", str(image["url"]))
            if node.get("isAccessibleForFree") is False:
                found["locked"] = "1"
    return found


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _language(soup: BeautifulSoup, text: str) -> str | None:
    root = soup.find("html")
    lang = root.get("lang") if root else None
    if lang and _LANG.match(str(lang).strip()):
        return str(lang).strip().lower()[:16]
    tokens = [word.strip(".,").lower() for word in text.split()]
    if sum(1 for word in tokens if word in _EN_STOPS) >= 3:
        return "en"
    return None


def _paywalled(html: str, linked: dict[str, str]) -> bool:
    if linked.get("locked"):
        return True
    lowered = html.lower()
    markers = (
        "subscribe to continue",
        'class="paywall"',
        "article:content_tier",
        "isaccessibleforfree",
    )
    if "isaccessibleforfree" in lowered and "false" in lowered:
        return True
    if "article:content_tier" in lowered and "locked" in lowered:
        return True
    return any(marker in lowered for marker in markers[:2])
