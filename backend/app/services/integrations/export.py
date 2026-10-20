"""PKM integrations — export saved/highlighted items.

- Obsidian: Markdown files (one per item), dropped into a vault folder. No API
  key needed — the user downloads a zip or copies into their vault.
- Logseq: the same saved items as Logseq pages (EC-05).

Both read from the same source: items the user has saved
(`UserContentInteraction.saved == True`). The Notion and Readwise API
exporters were removed in #258 — unused, and the Markdown zip + webhook
cover the same needs without third-party API churn.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def _get_saved_items(
    user_id: uuid.UUID, session: AsyncSession
) -> list[tuple[ContentItem, UserContentInteraction]]:
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
    return [(row[0], row[1]) for row in result.all()]


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
        else datetime.now(UTC).isoformat()
    )
    reading_time = (
        content.reading_time_minutes if content.reading_time_minutes is not None else "unknown"
    )
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


async def export_to_obsidian(user_id: uuid.UUID, session: AsyncSession) -> list[dict]:
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


def _to_logseq(content: ContentItem, interaction: UserContentInteraction) -> tuple[str, str]:
    """Render one saved item as a Logseq-flavored Markdown page (EC-05).

    Logseq pages use `key:: value` property lines under a heading and
    [[wiki-links]]; journals-style bullets keep the body scannable.
    """
    saved_at = (
        interaction.saved_read_at.isoformat()
        if interaction.saved_read_at
        else datetime.now(UTC).isoformat()
    )
    props = [
        f"source:: {content.url}",
        f"author:: {content.author or 'unknown'}",
        f"saved:: {saved_at}",
        "type:: weirling",
    ]
    if content.topic_clusters:
        props.append("topics:: " + " ".join(f"[[{t}]]" for t in content.topic_clusters[:5]))

    lines = [f"- ## {content.title}", ""]
    lines += [f"- {p}" for p in props]
    lines.append("")
    if content.summary_brief:
        lines.append(f"- > {content.summary_brief}")
    if content.full_text:
        for paragraph in content.full_text.split("\n\n")[:40]:
            text = paragraph.strip()
            if text:
                lines.append(f"- {text}")
    else:
        lines.append(f"- [Read original]({content.url})")
    lines.append(f"- original:: [{content.url}]({content.url})")
    # Short unique suffix keeps page names distinct when titles collide
    # (CodeRabbit): a duplicate filename would overwrite on import.
    import hashlib

    uid = str(content.id)[:8] if content.id else hashlib.sha1(content.url.encode()).hexdigest()[:8]
    return f"weirling/{_slugify(content.title)}-{uid}.md", "\n".join(lines) + "\n"


async def export_to_logseq(user_id: uuid.UUID, session: AsyncSession) -> list[dict]:
    """Saved items as Logseq pages under a weirling/ folder (EC-05)."""
    items = await _get_saved_items(user_id, session)
    out: list[dict] = []
    for content, interaction in items:
        filename, body = _to_logseq(content, interaction)
        out.append({"filename": filename, "content": body})
    logger.info(f"Logseq export for user {user_id}: {len(out)} items")
    return out
