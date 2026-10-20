"""Discovery pool: interest-adjacent items from outside the user's feeds (#141).

Nothing used to create `origin="discovery"` items, so on a single-user
instance (no other users' feeds to borrow from) the Discovery section was
always empty. Each day, per user:

1. outbound links in articles the user finished in the last week, if they
   point outside the user's feeds and fetch as articles (robots.txt,
   politeness and SSRF rules apply via `scrape_page`);
2. if that leaves room, the newest item from unfollowed feeds in starter
   packs that match the user's top interests.

Items are public and shared (another user can see the same article), carry
`discovered_via` for the card label, and are capped per user per day.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.interest_graph import InterestNode
from app.models.source import Source
from app.utils.logging import get_logger

logger = get_logger(__name__)

PER_USER_PER_DAY = 4
READ_WINDOW = timedelta(days=7)
MIN_WORDS = 150
# Link targets that are rarely readable articles.
SKIP_HOSTS = frozenset(
    {
        "twitter.com",
        "x.com",
        "t.co",
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "youtube.com",
        "youtu.be",
        "tiktok.com",
        "reddit.com",
        "news.ycombinator.com",
        "github.com",
        "gist.github.com",
        "web.archive.org",
        "amazon.com",
        "apps.apple.com",
        "play.google.com",
    }
)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


async def _existing_urls(session: AsyncSession, urls: list[str]) -> set[str]:
    if not urls:
        return set()
    rows = await session.execute(select(ContentItem.url).where(ContentItem.url.in_(urls)))
    return {row[0] for row in rows.all()}


async def _store(session: AsyncSession, raw, via: str, now: datetime) -> uuid.UUID | None:
    from app.services.takedown import is_url_blocked

    if await is_url_blocked(session, raw.url):
        return None
    result = await session.execute(
        insert(ContentItem)
        .values(
            url=raw.url,
            title=(raw.title or raw.url)[:500],
            author=raw.author,
            published_at=raw.published_at,
            full_text=raw.full_text,
            word_count=raw.word_count,
            language=raw.language,
            lead_image_url=raw.lead_image_url,
            paywalled=raw.paywalled,
            rankable=raw.rankable,
            page_type=raw.page_type,
            origin="discovery",
            discovered_via=via[:200],
            fetched_at=now,
        )
        .on_conflict_do_nothing()
        .returning(ContentItem.id)
    )
    return result.scalar_one_or_none()


def _usable(raw) -> bool:
    return bool(
        raw is not None
        and raw.rankable
        and not raw.paywalled
        and (raw.word_count or 0) >= MIN_WORDS
        and raw.page_type in (None, "article")
    )


async def refresh_for_user(
    user_id: uuid.UUID,
    session: AsyncSession,
    *,
    now: datetime | None = None,
    scrape: Callable[[str], Awaitable] | None = None,
    fetch_feed: Callable[[str], Awaitable] | None = None,
    feed_cache: dict | None = None,
    limit: int = PER_USER_PER_DAY,
) -> list[uuid.UUID]:
    """Add up to `limit` discovery items for this user; returns new item ids."""
    from app.services.ingestion.rss_parser import fetch_feed as default_fetch_feed
    from app.services.ingestion.scraper import scrape_page
    from app.services.ranking.interests import outbound_links

    scrape_fn: Callable[[str], Awaitable] = scrape or scrape_page
    fetch_feed_fn: Callable[[str], Awaitable] = fetch_feed or default_fetch_feed
    now = now or datetime.now(UTC)
    feed_cache = {} if feed_cache is None else feed_cache

    own = list((await session.execute(select(Source).where(Source.user_id == user_id))).scalars())
    followed_hosts = {_host(s.url) for s in own} | {_host(s.feed_url) for s in own if s.feed_url}
    followed_feeds = {(s.feed_url or s.url) for s in own}
    new_ids: list[uuid.UUID] = []

    # 1. Outbound links from what the user finished recently.
    reads = (
        await session.execute(
            select(ContentItem.url, ContentItem.full_text, Source.name)
            .join(UserContentInteraction, UserContentInteraction.content_item_id == ContentItem.id)
            .outerjoin(Source, Source.id == ContentItem.source_id)
            .where(
                UserContentInteraction.user_id == user_id,
                UserContentInteraction.read_completion_pct >= 0.7,
                UserContentInteraction.opened_at >= now - READ_WINDOW,
                ContentItem.full_text.isnot(None),
            )
            .order_by(UserContentInteraction.opened_at.desc())
            .limit(20)
        )
    ).all()
    candidates: list[tuple[str, str]] = []
    for url, text, source_name in reads:
        for link in outbound_links(text or "", source_host=_host(url)):
            host = _host(link)
            if not host or host in SKIP_HOSTS or host in followed_hosts:
                continue
            candidates.append((link, f"a link in {source_name or _host(url)}"))
    known = await _existing_urls(session, [c[0] for c in candidates])
    seen: set[str] = set()
    for link, via in candidates:
        if len(new_ids) >= limit:
            break
        if link in known or link in seen:
            continue
        seen.add(link)
        try:
            raw = await scrape_fn(link)
        except Exception as e:
            logger.info(f"discovery: could not fetch {link}: {e}")
            continue
        if _usable(raw):
            raw.url = link
            item_id = await _store(session, raw, via, now)
            if item_id:
                new_ids.append(item_id)

    # 2. Unfollowed starter-pack feeds that match the user's interests.
    if len(new_ids) < limit:
        from app.services.cold_start.starter_packs import list_starter_packs

        labels = [
            row[0].lower()
            for row in (
                await session.execute(
                    select(InterestNode.topic_label)
                    .where(InterestNode.user_id == user_id)
                    .order_by(InterestNode.weight.desc())
                    .limit(8)
                )
            ).all()
        ]
        words = {w for label in labels for w in label.replace("&", " ").split() if len(w) > 2}
        for pack in list_starter_packs():
            if len(new_ids) >= limit:
                break
            pack_words = {w for w in pack.title.lower().replace("&", " ").split() if len(w) > 2}
            if pack.title.lower() not in labels and not (words & pack_words):
                continue
            for feed in pack.feeds:
                if len(new_ids) >= limit:
                    break
                feed_url = feed["feed_url"]
                if feed_url in followed_feeds:
                    continue
                if feed_url not in feed_cache:
                    try:
                        feed_cache[feed_url] = await fetch_feed_fn(feed_url)
                    except Exception as e:
                        logger.info(f"discovery: could not fetch pack feed {feed_url}: {e}")
                        feed_cache[feed_url] = None
                fetched = feed_cache[feed_url]
                items = list(getattr(fetched, "items", None) or [])
                if not items:
                    continue
                newest = max(
                    items, key=lambda r: r.published_at or datetime.min.replace(tzinfo=UTC)
                )
                if newest.url in await _existing_urls(session, [newest.url]):
                    continue
                item_id = await _store(session, newest, f"the {pack.title} starter pack", now)
                if item_id:
                    new_ids.append(item_id)

    await session.flush()
    return new_ids
