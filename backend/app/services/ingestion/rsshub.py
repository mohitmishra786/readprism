"""Optional RSSHub routes for platforms that have no native feed.

An empty ``RSSHUB_BASE_URL`` builds no URLs and the health check does not
call the network. Routes are best-effort. LinkedIn and other closed networks
stay unsupported on purpose.
"""

from __future__ import annotations

from urllib.parse import urlparse

from app.config import get_settings

# path templates. {user} is the first path segment, or the host's handle.
ROUTES: dict[str, str] = {
    "twitter.com": "/twitter/user/{user}",
    "x.com": "/twitter/user/{user}",
    "instagram.com": "/instagram/user/{user}",
    "threads.net": "/threads/{user}",
    "pixiv.net": "/pixiv/user/{user}",
    "weibo.com": "/weibo/user/{user}",
}

TIER = "best-effort"


def configured_base() -> str:
    return get_settings().rsshub_base_url.strip().rstrip("/")


def candidate_urls(page_url: str, base: str | None = None) -> list[str]:
    root = (base if base is not None else configured_base()).strip().rstrip("/")
    if not root:
        return []
    parsed = urlparse(page_url)
    host = parsed.netloc.lower().removeprefix("www.")
    template = ROUTES.get(host)
    if template is None:
        return []
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return []
    user = parts[0].lstrip("@")
    if not user:
        return []
    return [root + template.format(user=user)]


def health_url(base: str | None = None) -> str | None:
    root = (base if base is not None else configured_base()).strip().rstrip("/")
    if not root:
        return None
    return root + "/"


async def rsshub_is_healthy(fetch) -> bool | None:
    """None when RSSHub is disabled. Otherwise True only on HTTP 200."""
    target = health_url()
    if target is None:
        return None
    status = await fetch(target)
    return status == 200
