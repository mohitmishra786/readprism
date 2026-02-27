from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.digest import Digest, DigestItem
from app.models.user import User
from app.utils.email import send_email
from app.utils.logging import get_logger

logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "templates"

_jinja_env: Optional[Environment] = None


def _get_jinja_env() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html"]),
        )
    return _jinja_env


SIGNAL_LABELS = {
    "semantic": "matches your interests",
    "reading_depth": "matches your reading depth preference",
    "suggestion": "similar to content you've discovered",
    "explicit_feedback": "aligns with your ratings",
    "source_trust": "from a highly trusted source",
    "content_quality": "high quality content",
    "temporal_context": "matches your current focus",
    "novelty": "expands your usual reading",
}


def _top_signals(breakdown: dict, n: int = 2) -> list[str]:
    sorted_signals = sorted(
        [(k, v) for k, v in breakdown.items() if not k.startswith("_")],
        key=lambda x: x[1],
        reverse=True,
    )
    return [SIGNAL_LABELS.get(k, k) for k, _ in sorted_signals[:n]]


async def deliver_digest(digest: Digest, user: User, session: AsyncSession) -> bool:
    # Load digest items with content
    items_result = await session.execute(
        select(DigestItem)
        .where(DigestItem.digest_id == digest.id)
        .order_by(DigestItem.position)
    )
    digest_items = list(items_result.scalars().all())

    content_ids = [di.content_item_id for di in digest_items]
    content_result = await session.execute(
        select(ContentItem).where(ContentItem.id.in_(content_ids))
    )
    content_map = {c.id: c for c in content_result.scalars().all()}

    # Group by section
    sections: dict[str, list[dict]] = {}
    for di in digest_items:
        content = content_map.get(di.content_item_id)
        if not content:
            continue
        section = di.section
        if section not in sections:
            sections[section] = []
        sections[section].append({
            "content": content,
            "prs_score": di.prs_score,
            "signal_breakdown": di.signal_breakdown,
            "why_ranked": _top_signals(di.signal_breakdown or {}),
            "is_discovery": section == "discovery",
            "position": di.position,
        })

    # Build email HTML
    env = _get_jinja_env()
    try:
        template = env.get_template("digest_email.html")
        html_body = template.render(
            user=user,
            digest=digest,
            sections=sections,
            generated_at=digest.generated_at.strftime("%B %d, %Y"),
        )
    except Exception as e:
        logger.error(f"Failed to render digest email template: {e}")
        html_body = _fallback_html(user, sections)

    # Plain text fallback
    text_body = _build_text_body(user, sections)

    subject = f"Your ReadPrism Digest — {digest.generated_at.strftime('%B %d, %Y')}"
    success = await send_email(
        to=user.email,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
    )

    if success:
        digest.delivered_at = datetime.now(timezone.utc)
        await session.flush()

    return success


def _fallback_html(user: User, sections: dict) -> str:
    parts = [f"<h1>Your ReadPrism Digest</h1>"]
    for section_name, items in sections.items():
        parts.append(f"<h2>{section_name.replace('_', ' ').title()}</h2>")
        for item_data in items:
            content = item_data["content"]
            parts.append(f'<div><h3><a href="{content.url}">{content.title}</a></h3>')
            if content.summary_brief:
                parts.append(f"<p>{content.summary_brief}</p>")
            parts.append("</div>")
    return "".join(parts)


def _build_text_body(user: User, sections: dict) -> str:
    lines = [f"Your ReadPrism Digest\n", "=" * 40]
    for section_name, items in sections.items():
        lines.append(f"\n{section_name.upper().replace('_', ' ')}\n" + "-" * 30)
        for item_data in items:
            content = item_data["content"]
            lines.append(f"\n{content.title}")
            if content.summary_brief:
                lines.append(content.summary_brief)
            lines.append(f"Read: {content.url}")
    return "\n".join(lines)
