"""Extraction cascade: feed text, trafilatura, readability, then rendered HTML.

Listing, collection, and product pages are extracted but marked unrankable.
A visible failure is ``method="failed"`` with empty text. Playwright is the
caller's last step: pass the rendered HTML in and label it ``playwright``.
"""

from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup

MIN_USEFUL_WORDS = 40
MIN_FEED_WORDS = 80
UNRANKABLE = {"listing", "collection", "product"}


@dataclass
class Extraction:
    text: str
    method: str
    confidence: float
    page_type: str

    @property
    def rankable(self) -> bool:
        return self.page_type not in UNRANKABLE and self.method != "failed"


def looks_js_only(html: str) -> bool:
    if not html:
        return False
    text = _plain(html)
    if len(text.split()) >= 20:
        return False
    lowered = html.lower()
    return 'id="__next"' in lowered or 'id="app"' in lowered or "<script" in lowered


def page_type_of(html: str) -> str:
    if not html:
        return "unknown"
    lowered = html.lower()
    if (
        'og:type" content="product"' in lowered
        or "schema.org/product" in lowered
        or "add to cart" in lowered
    ):
        return "product"
    if lowered.count("<article") >= 4 or 'class="listing"' in lowered:
        return "listing"
    if 'class="collection"' in lowered or (lowered.count("<h2") >= 6 and lowered.count("<p") < 3):
        return "collection"
    if "<article" in lowered or "<main" in lowered or lowered.count("<p") >= 2:
        return "article"
    return "unknown"


def extract_html(
    html: str,
    url: str = "",
    *,
    feed_text: str | None = None,
    rendered_html: str | None = None,
) -> Extraction:
    kind = page_type_of(html or rendered_html or "")
    feed = (feed_text or "").strip()
    if len(feed.split()) >= MIN_FEED_WORDS:
        return Extraction(feed, "feed", 0.95, "article" if kind == "unknown" else kind)

    extracted = _trafilatura(html, url)
    if len(extracted.split()) >= MIN_USEFUL_WORDS:
        return Extraction(extracted, "trafilatura", 0.8, kind)

    readable = _readability(html)
    if len(readable.split()) >= MIN_USEFUL_WORDS:
        return Extraction(readable, "readability", 0.6, kind)

    if rendered_html:
        rendered_text = _trafilatura(rendered_html, url) or _readability(rendered_html)
        if len(rendered_text.split()) >= MIN_USEFUL_WORDS:
            return Extraction(rendered_text, "playwright", 0.5, page_type_of(rendered_html))

    return Extraction("", "failed", 0.0, kind)


def from_feed_text(text: str | None) -> Extraction:
    body = (text or "").strip()
    words = len(body.split())
    if words >= MIN_FEED_WORDS:
        return Extraction(body, "feed", 0.9, "article")
    if words > 0:
        return Extraction(body, "feed", 0.4, "article")
    return Extraction("", "failed", 0.0, "unknown")


def _trafilatura(html: str, url: str) -> str:
    if not html:
        return ""
    try:
        import trafilatura

        text = trafilatura.extract(
            html,
            url=url or None,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )
    except Exception:
        return ""
    return (text or "").strip()


def _readability(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()
    node = soup.find("article") or soup.find("main") or soup.body or soup
    parts = [p.get_text(" ", strip=True) for p in node.find_all("p")]
    if not parts:
        return node.get_text(" ", strip=True)
    return " ".join(part for part in parts if part).strip()


def _plain(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
