"""The weekly 'What I learned about you' email (#184).

Built only from the reader's own interactions: what they finished, saved or
rated up this week compared with the week before.

- rising: up to 3 topics whose engagement grew most this week;
- fading: the strongest interest the reader didn't engage with this week;
- top source: where they finished the most articles this week.

Each topic carries a signed one-click undo ("less like this" for a rising
topic, "keep it" for a fading one) that adjusts the interest graph after a
POST confirmation, like the digest's rating links.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.interest_graph import InterestNode
from app.models.source import Source
from app.models.user import User

FINISHED = 0.85


@dataclass
class WeeklyLearning:
    rising: list[tuple[str, int, int]] = field(default_factory=list)  # topic, this week, last week
    fading: str | None = None
    top_source: tuple[str, int] | None = None  # name, articles finished

    @property
    def empty(self) -> bool:
        return not (self.rising or self.fading or self.top_source)


def _engagement(ix: UserContentInteraction) -> int:
    score = 0
    if (ix.read_completion_pct or 0) >= FINISHED or ix.reached_end:
        score += 1
    if (ix.explicit_rating or 0) > 0:
        score += 1
    if ix.saved:
        score += 1
    return score


def _aware(moment: datetime | None, now: datetime) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=now.tzinfo)


async def compute(user: User, session: AsyncSession, now: datetime) -> WeeklyLearning:
    week_start = now - timedelta(days=7)
    prev_start = now - timedelta(days=14)
    rows = (
        await session.execute(
            select(UserContentInteraction, ContentItem)
            .join(ContentItem, ContentItem.id == UserContentInteraction.content_item_id)
            .where(
                UserContentInteraction.user_id == user.id,
                UserContentInteraction.created_at >= prev_start,
            )
        )
    ).all()

    this_week: dict[str, int] = {}
    last_week: dict[str, int] = {}
    finished_by_source: dict = {}
    for ix, item in rows:
        when = _aware(ix.opened_at or ix.created_at, now) or now
        score = _engagement(ix)
        if score == 0:
            continue
        bucket = this_week if when >= week_start else last_week
        for topic in (item.topic_clusters or [])[:2]:
            bucket[topic] = bucket.get(topic, 0) + score
        if (
            when >= week_start
            and item.source_id
            and ((ix.read_completion_pct or 0) >= FINISHED or ix.reached_end)
        ):
            finished_by_source[item.source_id] = finished_by_source.get(item.source_id, 0) + 1

    learning = WeeklyLearning()
    growth = sorted(
        ((t, n, last_week.get(t, 0)) for t, n in this_week.items() if n > last_week.get(t, 0)),
        key=lambda row: (row[1] - row[2], row[1]),
        reverse=True,
    )
    learning.rising = growth[:3]

    rising = {t for t, _, _ in learning.rising}
    nodes = (
        await session.execute(
            select(InterestNode)
            .where(InterestNode.user_id == user.id, InterestNode.weight >= 0.4)
            .order_by(InterestNode.weight.desc())
        )
    ).scalars()
    for node in nodes:
        if node.topic_label in this_week or node.topic_label in rising:
            continue
        muted_until = _aware(node.suppressed_until, now)
        if muted_until is not None and muted_until > now:
            continue
        learning.fading = node.topic_label
        break

    if finished_by_source:
        source_id, count = max(finished_by_source.items(), key=lambda kv: kv[1])
        source = await session.get(Source, source_id)
        if source is not None and source.user_id == user.id:
            learning.top_source = (source.name or source.url, count)
    return learning


def render(
    user: User, learning: WeeklyLearning, *, links: dict, frontend_url: str, unsubscribe: str
) -> tuple[str, str]:
    """(html, text). `links` maps (topic, action) -> signed URL."""
    esc = html.escape
    parts = [
        '<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:560px;margin:0 auto;color:#1c1917">',
        '<h1 style="font-size:20px">What ReadPrism learned about you this week</h1>',
    ]
    text = ["What ReadPrism learned about you this week", ""]
    if learning.rising:
        parts.append('<h2 style="font-size:15px">Rising</h2><ul>')
        text.append("Rising:")
        for topic, now_n, before_n in learning.rising:
            link = links[(topic, "less")]
            parts.append(
                f"<li><strong>{esc(topic)}</strong>: you engaged with it {now_n} times "
                f'(last week {before_n}). <a href="{esc(link, quote=True)}">Less like this</a></li>'
            )
            text.append(
                f"- {topic}: {now_n} this week (last week {before_n}). Less like this: {link}"
            )
        parts.append("</ul>")
        text.append("")
    if learning.fading:
        link = links[(learning.fading, "more")]
        parts.append(
            f'<h2 style="font-size:15px">Fading</h2><p><strong>{esc(learning.fading)}</strong> is a strong '
            f"interest you didn't read this week. ReadPrism will show it a little less unless you "
            f'<a href="{esc(link, quote=True)}">keep it</a>.</p>'
        )
        text += [f"Fading: {learning.fading}. Keep it: {link}", ""]
    if learning.top_source:
        name, count = learning.top_source
        parts.append(
            f"<p>The source you finished most: <strong>{esc(name)}</strong> ({count} articles).</p>"
        )
        text += [f"The source you finished most: {name} ({count} articles).", ""]
    parts.append(
        f'<p><a href="{esc(frontend_url, quote=True)}/interests">See and edit everything ReadPrism has learned</a></p>'
        f'<p style="font-size:12px;color:#78716c">You get this because you turned on the weekly summary. '
        f'<a href="{esc(unsubscribe, quote=True)}" style="color:#78716c">Turn it off</a></p></div>'
    )
    text += [
        f"See and edit everything: {frontend_url}/interests",
        f"Turn off this email: {unsubscribe}",
    ]
    return "".join(parts), "\n".join(text)
