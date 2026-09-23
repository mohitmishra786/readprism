"""Server-side HTML sanitization for ingested content.

RSS bodies, scraped articles, and newsletter HTML are stored and later rendered
in the reader and in email. `nh3` (Ammonia) applies an allowlist: executable
tags, event handlers, and non-http(s) URLs are dropped, and links get
`rel="noopener noreferrer"`. The reader also runs DOMPurify, and the digest
template autoescapes. Either layer is sufficient; both are required.
"""

from __future__ import annotations

import nh3

from app.utils.logging import get_logger

logger = get_logger(__name__)

# Article formatting only. No svg/math (script gadgets), no style, no forms.
_ALLOWED_TAGS = {
    "a",
    "abbr",
    "b",
    "blockquote",
    "br",
    "code",
    "dd",
    "del",
    "div",
    "dl",
    "dt",
    "em",
    "figcaption",
    "figure",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "q",
    "s",
    "span",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}

# Drop the element *and* its text for tags whose contents are code, not prose.
_DROP_CONTENT_TAGS = {"script", "style", "iframe", "object", "embed", "noscript"}


def sanitize_stored_html(html: str) -> str:
    """Return an allowlisted HTML fragment, or "" if sanitization fails."""
    if not html:
        return html
    try:
        return nh3.clean(
            html,
            tags=_ALLOWED_TAGS,
            clean_content_tags=_DROP_CONTENT_TAGS,
            url_schemes={"http", "https", "mailto"},
            link_rel="noopener noreferrer",
            strip_comments=True,
        )
    except Exception as e:  # pragma: no cover - never let sanitization crash ingest
        logger.warning(f"HTML sanitization failed, dropping markup: {e}")
        return ""
