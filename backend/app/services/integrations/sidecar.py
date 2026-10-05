"""Sidecar import from Miniflux / FreshRSS (EC-07, D-14).

Subscriptions become Sources (deduped by feed URL, trust 0.45 like seeded
packs). For Miniflux, recently-read entry URLs that already exist as the
user's items get an opened interaction so ranking starts warm. All calls go
through safe_fetch with require_https (credentials never travel cleartext).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.source import Source
from app.models.user import User
from app.utils.logging import get_logger
from app.utils.ssrf import safe_fetch

logger = get_logger(__name__)


@dataclass
class SidecarResult:
    feeds_added: int = 0
    feeds_existing: int = 0
    read_marked: int = 0
    errors: list[str] = field(default_factory=list)


async def _add_feeds(user: User, feeds: list[dict], session: AsyncSession) -> SidecarResult:
    result = SidecarResult()
    existing = {
        row[0]
        for row in (
            await session.execute(select(Source.url).where(Source.user_id == user.id))
        ).fetchall()
    }
    for feed in feeds[:200]:
        url = feed.get("feed_url") or feed.get("url") or feed.get("site_url") or ""
        if not url.startswith("http"):
            continue
        if url in existing:
            result.feeds_existing += 1
            continue
        session.add(
            Source(
                user_id=user.id,
                url=url,
                name=(feed.get("title") or url)[:200],
                feed_url=url,
                source_type="rss",
                trust_weight=0.45,  # imported: prove itself like seeded packs
            )
        )
        existing.add(url)
        result.feeds_added += 1
    await session.flush()
    return result


async def _safe_get(url: str, **kwargs) -> httpx.Response | None:
    """safe_fetch wrapper for sidecar calls: auth headers must never be
    replayed on a redirect hop, so redirects are disabled outright
    (CodeRabbit CWE-200); failures become None (graceful)."""
    try:
        return await safe_fetch(url, method="GET", require_https=True, max_redirects=0, **kwargs)
    except Exception as e:
        logger.info(f"Sidecar fetch failed for {url}: {e}")
        return None


async def _sidecar_post(url: str, content: bytes) -> httpx.Response | None:
    """safe_fetch POST wrapper: no redirects, credentials in the body only."""
    try:
        return await safe_fetch(
            url,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            content=content,
            require_https=True,
            max_redirects=0,
        )
    except Exception as e:
        logger.info(f"Sidecar POST failed for {url}: {e}")
        return None


async def import_from_miniflux(
    user: User, base_url: str, token: str, session: AsyncSession
) -> SidecarResult:
    """Miniflux: /v1/feeds (X-Auth-Token) + /v1/entries?status=read."""
    base = base_url.rstrip("/")
    headers = {"X-Auth-Token": token}

    feeds: list[dict] = []
    # Miniflux caps the response; paginate so feed #201 is not silently
    # dropped with no retry path (CodeRabbit).
    for offset in range(0, 1000, 200):
        resp = await _safe_get(
            f"{base}/v1/feeds?limit=200&offset={offset}",
            headers=headers,
            max_bytes=2_000_000,
        )
        if resp is None:
            return SidecarResult(
                errors=["Miniflux fetch failed: unreachable, blocked, or not HTTPS"]
            )
        if resp.status_code != 200:
            return SidecarResult(errors=[f"Miniflux feed list failed: HTTP {resp.status_code}"])
        data = json.loads(resp.content.decode("utf-8", errors="replace"))
        # Miniflux returns a JSON array; tolerate a {"feeds": []} envelope too.
        page = data if isinstance(data, list) else data.get("feeds", [])
        if not page:
            break
        feeds.extend(page)
        if len(page) < 200:
            break
    result = await _add_feeds(user, feeds, session)

    # Read state: mark already-ingested matching items as opened.
    entries_resp = await _safe_get(
        f"{base}/v1/entries?status=read&limit=100", headers=headers, max_bytes=2_000_000
    )
    if entries_resp is None or entries_resp.status_code != 200:
        status = entries_resp.status_code if entries_resp is not None else "unreachable"
        result.errors.append(f"Miniflux read-state fetch failed: HTTP {status}")
    else:
        read_urls = {
            e.get("url")
            for e in json.loads(entries_resp.content.decode("utf-8", errors="replace")).get(
                "entries", []
            )
        }
        read_urls.discard(None)
        if read_urls:
            rows = await session.execute(select(ContentItem).where(ContentItem.url.in_(read_urls)))
            for item in rows.scalars():
                ix = await session.execute(
                    select(UserContentInteraction).where(
                        UserContentInteraction.user_id == user.id,
                        UserContentInteraction.content_item_id == item.id,
                    )
                )
                interaction = ix.scalar_one_or_none()
                if interaction is None:
                    session.add(
                        UserContentInteraction(
                            user_id=user.id,
                            content_item_id=item.id,
                            opened_at=item.fetched_at,
                            read_completion_pct=0.9,
                        )
                    )
                    result.read_marked += 1
                elif interaction.opened_at is None:
                    interaction.opened_at = item.fetched_at
                    result.read_marked += 1
            await session.flush()

    logger.info(f"Miniflux import for {user.id}: +{result.feeds_added} feeds")
    return result


async def import_from_freshrss(
    user: User, base_url: str, username: str, app_password: str, session: AsyncSession
) -> SidecarResult:
    """FreshRSS via its Google-Reader-compatible API (subscriptions only)."""
    base = base_url.rstrip("/")
    endpoint = f"{base}/api/greader.php"
    # Credentials travel in the POST body only — never the URL, where they
    # would land in request logs (CodeRabbit CWE-598).
    login = await _sidecar_post(
        f"{endpoint}/accounts/ClientLogin",
        content=f"Email={username}&Passwd={app_password}".encode(),
    )
    if login is None:
        return SidecarResult(errors=["FreshRSS login failed: unreachable, blocked, or not HTTPS"])
    if login.status_code != 200 or b"Auth=" not in login.content:
        return SidecarResult(errors=["FreshRSS login failed (check URL/user/app password)"])
    auth_token = login.content.decode().split("Auth=")[-1].strip().splitlines()[0]

    subs = await _safe_get(
        f"{endpoint}/reader/api/0/subscription/list?output=json",
        headers={"Authorization": f"GoogleLogin auth={auth_token}"},
    )
    if subs is None or subs.status_code != 200:
        status = subs.status_code if subs is not None else "unreachable"
        return SidecarResult(errors=[f"FreshRSS subscription list failed: HTTP {status}"])
    feeds = json.loads(subs.content.decode("utf-8", errors="replace")).get("subscriptions", [])
    result = await _add_feeds(user, feeds, session)
    logger.info(f"FreshRSS import for {user.id}: +{result.feeds_added} feeds")
    return result
