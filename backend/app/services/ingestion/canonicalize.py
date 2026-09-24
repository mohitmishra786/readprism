"""URL identity for dedupe. Tracking parameters are not part of the article."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "igshid",
}


def canonicalize_url(url: str) -> str | None:
    """Return a canonical URL, or None when the URL cannot be parsed.

    A bad port (`https://example.com:bad/a`) raises ValueError on `parsed.port`.
    Callers skip that item and keep the rest of the batch.
    """
    try:
        parsed = urlparse(url.strip())
        port = parsed.port
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    if ":" in host:
        host = f"[{host}]"
    scheme = (parsed.scheme or "https").lower()
    default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
    if port and port != default_port:
        netloc = f"{host}:{port}"
    else:
        netloc = host
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not _is_tracking(key)
        ]
    )
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((scheme, netloc, path, "", query, ""))


def _is_tracking(key: str) -> bool:
    lowered = key.lower()
    return lowered.startswith("utm_") or lowered in _TRACKING
