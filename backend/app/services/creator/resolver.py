from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.creator import Creator, CreatorPlatform
from app.utils.logging import get_logger

logger = get_logger(__name__)

PLATFORM_DOMAINS = {
    "substack.com": "substack",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "medium.com": "medium",
    "linkedin.com": "linkedin",
    "spotify.com": "podcast",
    "open.spotify.com": "podcast",
}


@dataclass
class CreatorResolutionResult:
    creator: Creator
    platforms_discovered: int
    warning: Optional[str] = None


def _detect_platform(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower().lstrip("www.")
    for domain, platform in PLATFORM_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return platform
    return "blog"


async def _fetch_page(url: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "ReadPrism/1.0"})
            return resp.text
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


def _extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    return match.group(1).strip() if match else "Unknown Creator"


def _autodiscover_feed_url(platform: str, profile_url: str, html: str) -> Optional[str]:
    parsed = urlparse(profile_url)
    username = parsed.path.strip("/").split("/")[-1].lstrip("@")

    if platform == "substack":
        host = parsed.netloc
        return f"https://{host}/feed"
    if platform == "medium":
        return f"https://medium.com/feed/@{username}"
    if platform == "youtube":
        channel_match = re.search(r'channel_id["\'\s]*[:=]["\'\s]*([UC][\w-]+)', html)
        if channel_match:
            cid = channel_match.group(1)
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
    if platform == "twitter":
        return None  # Twitter/X has no public RSS feed
    if platform == "linkedin":
        return None  # LinkedIn has no public RSS feed

    # Generic blog: try autodiscovery
    feed_match = re.search(
        r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*href=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if feed_match:
        href = feed_match.group(1)
        if href.startswith("http"):
            return href
        from urllib.parse import urljoin
        return urljoin(profile_url, href)
    return None


async def resolve_creator(
    name_or_url: str, user_id: uuid.UUID, session: AsyncSession
) -> CreatorResolutionResult:
    is_url = name_or_url.startswith("http")
    platforms_data: list[dict] = []
    display_name = name_or_url
    warning: Optional[str] = None

    if is_url:
        primary_platform = _detect_platform(name_or_url)

        # Early warning for platforms with no reliable public feed
        if primary_platform == "twitter":
            warning = (
                "Twitter/X does not provide a public RSS feed. "
                "ReadPrism cannot automatically track new posts from this profile. "
                "Consider adding the creator's Substack, newsletter, or personal blog instead."
            )
        elif primary_platform == "linkedin":
            warning = (
                "LinkedIn does not provide a public RSS feed. "
                "ReadPrism cannot automatically track new posts from this profile. "
                "Consider adding the creator's newsletter or personal blog instead."
            )

        html = await _fetch_page(name_or_url)
        if html:
            display_name = _extract_title(html)
            feed_url = _autodiscover_feed_url(primary_platform, name_or_url, html)
            platforms_data.append({
                "platform": primary_platform,
                "url": name_or_url,
                "feed_url": feed_url,
                "is_verified": True,
            })

            # Discover other platform links from bio
            additional = _find_additional_platforms(html, name_or_url)
            platforms_data.extend(additional)
        else:
            if not warning:
                warning = f"Could not fetch profile page: {name_or_url}"
            platforms_data.append({
                "platform": primary_platform,
                "url": name_or_url,
                "feed_url": None,
                "is_verified": False,
            })
    else:
        display_name = name_or_url
        warning = "Name-only creator added without URL. No feed discovered."

    # Create Creator
    creator = Creator(
        user_id=user_id,
        display_name=display_name[:200],
        resolved=len(platforms_data) > 0 and any(p["feed_url"] for p in platforms_data),
    )
    session.add(creator)
    await session.flush()

    # Create CreatorPlatform records
    for pd in platforms_data:
        cp = CreatorPlatform(
            creator_id=creator.id,
            platform=pd["platform"],
            platform_url=pd["url"],
            feed_url=pd.get("feed_url"),
            is_verified=pd.get("is_verified", False),
        )
        session.add(cp)
    await session.flush()

    if not any(p.get("feed_url") for p in platforms_data) and not warning:
        warning = "No RSS feed discovered. Content tracking may be limited."

    logger.info(f"Resolved creator {creator.id}: {len(platforms_data)} platforms")
    return CreatorResolutionResult(
        creator=creator,
        platforms_discovered=len(platforms_data),
        warning=warning,
    )


def _find_additional_platforms(html: str, source_url: str) -> list[dict]:
    """Scan bio/about section for links to other platforms."""
    additional: list[dict] = []
    source_host = urlparse(source_url).netloc

    link_pattern = re.compile(r'href=["\']((https?://)[^"\']+)["\']', re.IGNORECASE)
    for match in link_pattern.finditer(html):
        url = match.group(1)
        parsed = urlparse(url)
        host = parsed.netloc.lower().lstrip("www.")
        if host == source_host.lstrip("www."):
            continue
        platform = None
        for domain, pname in PLATFORM_DOMAINS.items():
            if host == domain or host.endswith("." + domain):
                platform = pname
                break
        if platform and not any(p["url"] == url for p in additional):
            feed_url = _autodiscover_feed_url(platform, url, "")
            additional.append({
                "platform": platform,
                "url": url,
                "feed_url": feed_url,
                "is_verified": False,
            })
        if len(additional) >= 4:
            break
    return additional
