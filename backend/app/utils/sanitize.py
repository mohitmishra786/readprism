"""Server-side HTML sanitization for ingested content (audit 06-7).

RSS `content`/`summary` fields arrive as raw third-party HTML and are stored in
`content_items.full_text`. The authoritative XSS gate is at the render boundary
(the reader sanitizes with DOMPurify; the digest email autoescapes), but we also
strip obviously-executable markup on the way *in* so no active payload is ever
persisted or served to a non-sanitizing consumer.

This is defense in depth, not the sole control: BeautifulSoup is not a
security-grade sanitizer, so the client-side DOMPurify pass remains required.
"""

from __future__ import annotations

from app.utils.logging import get_logger

logger = get_logger(__name__)

_DANGEROUS_TAGS = {
    "script",
    "style",
    "iframe",
    "object",
    "embed",
    "form",
    "link",
    "meta",
    "base",
    "noscript",
    "svg",
}


def sanitize_stored_html(html: str) -> str:
    """Remove executable elements, inline event handlers, and javascript: URLs."""
    if not html:
        return html
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover - bs4 is a hard dependency
        return html

    try:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(list(_DANGEROUS_TAGS)):
            tag.decompose()
        for el in soup.find_all(True):
            for attr in list(el.attrs):
                lattr = attr.lower()
                value = str(el.attrs.get(attr, "")).strip().lower()
                is_event_handler = lattr.startswith("on")
                is_dangerous_url = lattr in ("href", "src", "xlink:href") and value.startswith(
                    ("javascript:", "data:text/html", "vbscript:")
                )
                if is_event_handler or is_dangerous_url:
                    del el[attr]
        # Return the inner body markup (BeautifulSoup wraps fragments in html/body).
        if soup.body is not None:
            return soup.body.decode_contents()
        return str(soup)
    except Exception as e:  # pragma: no cover - never let sanitization crash ingest
        logger.warning(f"HTML sanitization failed, dropping markup: {e}")
        return ""
