"""Ranked feed discovery for a page URL.

Order, highest rank first: HTML `<link rel="alternate">`, a platform recipe,
a well-known path that actually looks like a feed, an RSSHub route when
`RSSHUB_BASE_URL` is set, then the page itself as a scrape candidate.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.config import get_settings
from app.utils.logging import get_logger, sanitize_log
from app.utils.ssrf import UnsafeURLError, safe_fetch, validate_public_url

logger = get_logger(__name__)

FetchText = Callable[[str], Awaitable[str | None]]

_WELL_KNOWN = (
    "/feed",
    "/feed/",
    "/rss",
    "/rss/",
    "/atom.xml",
    "/index.xml",
    "/feed.xml",
    "/rss.xml",
    "/feed/rss",
    "/feeds/posts/default",
    "/?feed=rss2",
)

_RANK = {"link": 100, "platform": 80, "well_known": 60, "rsshub": 40, "scrape": 10}


@dataclass(frozen=True)
class FeedCandidate:
    url: str
    method: str
    rank: int


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _segments(url: str) -> list[str]:
    return [part for part in urlparse(url).path.split("/") if part]


def link_candidates(page_url: str, html: str) -> list[FeedCandidate]:
    if not html:
        return []
    head = html.lstrip()[:80].lower()
    if head.startswith("<?xml") or head.startswith("<rss") or head.startswith("<feed"):
        return []
    soup = BeautifulSoup(html, "lxml")
    found: list[FeedCandidate] = []
    seen: set[str] = set()
    for tag in soup.find_all("link"):
        rel = " ".join(tag.get("rel") or []).lower()
        kind = (tag.get("type") or "").lower()
        href = tag.get("href")
        if not href or "alternate" not in rel:
            continue
        if "rss" not in kind and "atom" not in kind:
            continue
        absolute = href if href.startswith("http") else urljoin(page_url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        found.append(FeedCandidate(absolute, "link", _RANK["link"]))
    return found


def _hostname(url: str) -> str:
    """Parsed hostname, without a leading www. CodeQL treats this as a real host."""
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _is_host(url: str, domain: str) -> bool:
    host = _hostname(url)
    return host == domain or host.endswith("." + domain)


def platform_candidates(page_url: str, html: str) -> list[FeedCandidate]:
    parsed = urlparse(page_url)
    host = _hostname(page_url)
    parts = _segments(page_url)
    found: list[FeedCandidate] = []

    def add(url: str) -> None:
        found.append(FeedCandidate(url, "platform", _RANK["platform"]))

    if _is_host(page_url, "substack.com"):
        add(f"https://{parsed.netloc}/feed")
    if _is_host(page_url, "blogspot.com") or _is_host(page_url, "blogger.com"):
        add(urljoin(_origin(page_url) + "/", "feeds/posts/default"))
    if _is_host(page_url, "medium.com"):
        if host not in {"medium.com"} and host.endswith(".medium.com"):
            add(f"https://{parsed.netloc}/feed")
        else:
            username = next((part for part in parts if part.startswith("@")), "")
            publication = parts[0] if parts and not parts[0].startswith("@") else ""
            if username:
                add(f"https://medium.com/feed/{username}")
            elif publication and publication not in {"feed", "tag"}:
                add(f"https://medium.com/feed/{publication}")
    if _is_host(page_url, "reddit.com") and parts:
        if parts[0] in {"r", "user", "u"} and len(parts) >= 2:
            name = parts[1]
            kind = parts[0]
            if "top" in parts:
                add(f"https://www.reddit.com/{kind}/{name}/top/.rss?t=week")
            else:
                add(f"https://www.reddit.com/{kind}/{name}/.rss")
    if _is_host(page_url, "bsky.app") and len(parts) >= 2 and parts[0] == "profile":
        add(f"https://bsky.app/profile/{parts[1]}/rss")
    if parts and parts[0].startswith("@") and _is_host(page_url, "mastodon.social"):
        add(f"https://{parsed.hostname}/@{parts[0].lstrip('@')}.rss")
    if host in {"youtube.com", "youtu.be", "m.youtube.com"}:
        match = re.search(
            r"(?:channel_id|channelId)[\"'\s]*[:=][\"'\s]*([UC][\w-]{8,})", html or ""
        )
        if not match:
            match = re.search(
                r"itemprop=[\"']channelId[\"'][^>]*content=[\"']([UC][\w-]{8,})[\"']",
                html or "",
                re.IGNORECASE,
            )
        if match:
            add(f"https://www.youtube.com/feeds/videos.xml?channel_id={match.group(1)}")
    if host == "github.com" and len(parts) >= 2:
        owner, repo = parts[0], parts[1]
        add(f"https://github.com/{owner}/{repo}/releases.atom")
        add(f"https://github.com/{owner}/{repo}/commits.atom")
    if host == "arxiv.org":
        category = ""
        if parts[:1] in (["list"], ["rss"]) and len(parts) >= 2:
            category = parts[1]
        if category:
            add(f"https://rss.arxiv.org/rss/{category}")
    return found


def rsshub_candidates(page_url: str) -> list[FeedCandidate]:
    base = get_settings().rsshub_base_url.strip().rstrip("/")
    if not base:
        return []
    parsed = urlparse(page_url)
    host = parsed.netloc.lower().removeprefix("www.")
    parts = _segments(page_url)
    routes: list[str] = []
    if host in {"twitter.com", "x.com"} and parts:
        routes.append(f"{base}/twitter/user/{parts[0]}")
    if not routes:
        return []
    return [FeedCandidate(url, "rsshub", _RANK["rsshub"]) for url in routes]


def _looks_like_feed(text: str) -> bool:
    head = text[:800].lower()
    return "<rss" in head or "<feed" in head


async def _confirmed(candidates: list[FeedCandidate], getter: FetchText) -> list[FeedCandidate]:
    """Keep a recipe only after its URL returns feed XML. At most two probes at once."""
    if not candidates:
        return []
    gate = asyncio.Semaphore(2)

    async def _one(candidate: FeedCandidate) -> tuple[FeedCandidate, str | None]:
        async with gate:
            return candidate, await getter(candidate.url)

    checked = await asyncio.gather(*(_one(candidate) for candidate in candidates))
    return [candidate for candidate, body in checked if body and _looks_like_feed(body)]


async def _first_well_known(origin: str, getter: FetchText) -> FeedCandidate | None:
    targets = [urljoin(origin + "/", path.lstrip("/")) for path in _WELL_KNOWN]
    gate = asyncio.Semaphore(2)

    async def _one(index: int, target: str) -> tuple[int, str, str | None]:
        async with gate:
            return index, target, await getter(target)

    checked = await asyncio.gather(*(_one(index, target) for index, target in enumerate(targets)))
    for _index, target, body in sorted(checked):
        if body and _looks_like_feed(body):
            return FeedCandidate(target, "well_known", _RANK["well_known"])
    return None


async def _fetch_text(url: str) -> str | None:
    try:
        validate_public_url(url)
        resp = await safe_fetch(url, timeout=10, max_bytes=1_000_000)
    except (UnsafeURLError, Exception) as e:
        logger.debug("discovery fetch failed for %s: %s", sanitize_log(url), e)
        return None
    if resp.status_code != 200:
        return None
    return resp.text


async def discover_feed_candidates(
    page_url: str,
    *,
    html: str | None = None,
    fetch: FetchText | None = None,
) -> list[FeedCandidate]:
    """Return candidates best-first. The page is fetched when `html` is omitted."""
    getter = fetch or _fetch_text
    if html is None:
        html = await getter(page_url) or ""

    found: list[FeedCandidate] = []
    proposed = [*link_candidates(page_url, html), *platform_candidates(page_url, html)]
    found.extend(await _confirmed(proposed, getter))

    if not found:
        hit = await _first_well_known(_origin(page_url), getter)
        if hit is not None:
            found.append(hit)
        found.extend(await _confirmed(rsshub_candidates(page_url), getter))

    if not any(item.method != "scrape" for item in found):
        found.append(FeedCandidate(page_url, "scrape", _RANK["scrape"]))

    unique: list[FeedCandidate] = []
    seen: set[str] = set()
    for item in sorted(found, key=lambda candidate: candidate.rank, reverse=True):
        if item.url in seen:
            continue
        seen.add(item.url)
        unique.append(item)
    return unique


async def best_feed_url(
    page_url: str, *, html: str | None = None, fetch: FetchText | None = None
) -> str | None:
    """Highest candidate that is an actual feed. Scrape is not a feed URL."""
    for candidate in await discover_feed_candidates(page_url, html=html, fetch=fetch):
        if candidate.method != "scrape":
            return candidate.url
    return None
