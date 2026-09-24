"""Item identity beyond the raw feed link.

Canonical ``<link rel>`` and ``og:url`` win over the page URL. A feed ``guid``
is a second key so the same story with a new tracking link still matches.
"""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.services.ingestion.canonicalize import canonicalize_url
from app.utils.ssrf import UnsafeURLError, validate_public_url


def canonical_from_html(html: str, page_url: str) -> str | None:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    href = _link_href(soup, page_url)
    if href is None:
        meta = soup.find("meta", attrs={"property": "og:url"})
        content = meta.get("content") if meta else None
        if content:
            href = urljoin(page_url, str(content).strip())
    if not href:
        return None
    try:
        validate_public_url(href)
    except UnsafeURLError:
        return None
    return canonicalize_url(href)


def _link_href(soup: BeautifulSoup, page_url: str) -> str | None:
    for tag in soup.find_all("link"):
        rel = " ".join(tag.get("rel") or []).lower()
        if "canonical" not in rel:
            continue
        href = tag.get("href")
        if href:
            return urljoin(page_url, str(href).strip())
    return None


def apply_permanent_redirect(source, fetched_url: str, permanent: str | None) -> None:
    """Rewrite the URL we actually fetched when every hop was a 301."""
    if not permanent:
        return
    target = canonicalize_url(permanent) or permanent
    fetched = fetched_url.rstrip("/")
    feed = (source.feed_url or "").rstrip("/")
    page = (source.url or "").rstrip("/")
    if feed and feed == fetched:
        source.feed_url = target
    elif page == fetched:
        source.url = target
