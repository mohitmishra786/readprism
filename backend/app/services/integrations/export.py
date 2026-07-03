"""PKM integrations — export saved/highlighted items.

Three targets, each serving a different PKM workflow:
- Obsidian: Markdown files (one per item), dropped into a vault folder. No API
  key needed — the user downloads a zip or copies into their vault.
- Notion: pushes saved items to a database via the Notion API (user supplies an
  integration token + database id).
- Readwise: pushes saved items as "Reader" highlights via the Readwise API.

All three read from the same source: items the user has saved
(`UserContentInteraction.saved == True`) and optionally fully read.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def _get_saved_items(user_id: uuid.UUID, session: AsyncSession) -> list[tuple[ContentItem, UserContentInteraction]]:
    """Return (content, interaction) pairs for items the user has saved."""
    result = await session.execute(
        select(ContentItem, UserContentInteraction)
        .join(
            UserContentInteraction,
            (UserContentInteraction.content_item_id == ContentItem.id)
            & (UserContentInteraction.user_id == user_id),
        )
        .where(UserContentInteraction.saved.is_(True))
        .order_by(UserContentInteraction.created_at.desc())
    )
    return list(result.fetchall())


# ---------------------------------------------------------------------------
# Obsidian — Markdown export.
# ---------------------------------------------------------------------------

def _slugify(title: str, max_len: int = 80) -> str:
    """Make a filename-safe slug from a title."""
    keep = []
    for ch in title.strip():
        if ch.isalnum() or ch in (" ", "-", "_"):
            keep.append(ch)
        elif ch in ("/", "\\", ":", "."):
            keep.append("-")
    slug = "".join(keep).strip()
    # Collapse runs of whitespace/dashes into a single dash.
    while "  " in slug:
        slug = slug.replace("  ", " ")
    slug = slug.replace(" ", "-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return (slug or "untitled")[:max_len]


def _yaml_escape(value: str) -> str:
    """Quote a value for safe YAML frontmatter embedding.

    YAML interprets unquoted colons, leading special chars, etc. as structure.
    Always double-quote with escaped inner quotes — simplest safe approach.
    """
    if value is None:
        return '""'
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _to_markdown(content: ContentItem, interaction: UserContentInteraction) -> tuple[str, str]:
    """Render one saved item as Obsidian-flavored Markdown. Returns (filename, body)."""
    saved_at = (
        interaction.saved_read_at.isoformat()
        if interaction.saved_read_at
        else datetime.now(timezone.utc).isoformat()
    )
    reading_time = content.reading_time_minutes if content.reading_time_minutes is not None else "unknown"
    frontmatter = [
        "---",
        f"source: {_yaml_escape(content.url)}",
        f"author: {_yaml_escape(content.author or 'unknown')}",
        f"saved: {_yaml_escape(saved_at)}",
        f"reading_time: {_yaml_escape(str(reading_time))}",
        "---",
        "",
    ]
    lines = [f"# {content.title}", ""]
    if content.summary_detailed:
        lines += [f"> {content.summary_detailed}", ""]
    elif content.summary_brief:
        lines += [f"> {content.summary_brief}", ""]
    if content.full_text:
        # Cap to avoid gigantic notes.
        body = content.full_text[:20000]
        lines.append(body)
    else:
        lines.append(f"[Read original]({content.url})")
    lines += ["", "---", f"Original: [{content.url}]({content.url})", ""]
    return f"{_slugify(content.title)}.md", "\n".join(frontmatter + lines)


async def export_to_obsidian(
    user_id: uuid.UUID, session: AsyncSession
) -> list[dict]:
    """Return a list of {filename, content} dicts for Obsidian import.

    The frontend offers these as a zip download; the user drops them into a
    vault folder. No auth or network required.
    """
    items = await _get_saved_items(user_id, session)
    out: list[dict] = []
    for content, interaction in items:
        filename, body = _to_markdown(content, interaction)
        out.append({"filename": filename, "content": body})
    logger.info(f"Obsidian export for user {user_id}: {len(out)} items")
    return out


# ---------------------------------------------------------------------------
# Notion — push to a database.
# ---------------------------------------------------------------------------

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


async def export_to_notion(
    user_id: uuid.UUID,
    notion_token: str,
    database_id: str,
    session: AsyncSession,
) -> int:
    """Push saved items as rows in a Notion database. Returns the count pushed."""
    if not notion_token or not database_id:
        raise ValueError("Notion integration token and database id are required")

    items = await _get_saved_items(user_id, session)
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    pushed = 0
    async with httpx.AsyncClient(timeout=30) as client:
        for content, _interaction in items:
            properties = {
                "Name": {"title": [{"text": {"content": content.title[:100]}}]},
                "URL": {"url": content.url},
            }
            if content.author:
                properties["Author"] = {"rich_text": [{"text": {"content": content.author[:100]}}]}
            if content.summary_brief:
                properties["Summary"] = {
                    "rich_text": [{"text": {"content": content.summary_brief[:2000]}}]
                }
            payload = {"parent": {"database_id": database_id}, "properties": properties}
            try:
                resp = await client.post(
                    f"{NOTION_API}/pages", headers=headers, json=payload
                )
                if resp.status_code in (200, 201):
                    pushed += 1
                else:
                    logger.warning(f"Notion create failed ({resp.status_code}): {resp.text[:200]}")
            except Exception as e:
                logger.warning(f"Notion push error for item {content.id}: {e}")
    logger.info(f"Notion export for user {user_id}: {pushed}/{len(items)} pushed")
    return pushed


# ---------------------------------------------------------------------------
# Readwise — push as Reader highlights.
# ---------------------------------------------------------------------------

READWISE_API = "https://readwise.io/api/v2"


async def export_to_readwise(
    user_id: uuid.UUID, readwise_token: str, session: AsyncSession
) -> int:
    """Push saved items to Readwise as highlights. Returns count pushed.

    Uses the /highlights/ endpoint (the documented v2 API), where each saved
    item becomes a highlight whose required `text` field carries the summary or
    a link. The optional title/author/source_url give it Reader context.
    """
    if not readwise_token:
        raise ValueError("Readwise access token is required")

    items = await _get_saved_items(user_id, session)
    headers = {"Authorization": f"Token {readwise_token}", "Content-Type": "application/json"}
    highlights = [
        {
            # `text` is the only strictly-required field on the highlights endpoint.
            "text": (content.summary_brief or content.title)[:8000],
            "title": content.title,
            "author": content.author or "Unknown",
            "source_url": content.url,
            "category": "articles",
            "note": content.summary_detailed or "",
        }
        for content, _ in items
    ]
    pushed = 0
    async with httpx.AsyncClient(timeout=30) as client:
        # Push in batches of 50.
        for i in range(0, len(highlights), 50):
            batch = highlights[i : i + 50]
            try:
                resp = await client.post(
                    f"{READWISE_API}/highlights/", headers=headers, json={"highlights": batch}
                )
                if resp.status_code in (200, 201):
                    pushed += len(batch)
                else:
                    logger.warning(f"Readwise push failed ({resp.status_code}): {resp.text[:200]}")
            except Exception as e:
                logger.warning(f"Readwise push error: {e}")
    logger.info(f"Readwise export for user {user_id}: {pushed}/{len(items)} pushed")
    return pushed
