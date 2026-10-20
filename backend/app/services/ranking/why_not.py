"""'Why didn't I see this?' for any item (#267).

Scores one item for the current user with the live ranker (load_state +
score_candidates, the same path a digest build takes) and explains it in the
digest's own wording. Adds the verdict a digest card can't give: whether the
item was ever in one of the user's digests, and if not, why not.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.digest import Digest, DigestItem
from app.models.user import User
from app.services.ranking.contract import SIGNALS

# What the user can do to raise a signal, if it is the item's biggest gap.
_RAISE = {
    "semantic": "Add or boost the topic {topic} in your interests",
    "reading_depth": "Finish a few articles of this length; depth is learned from what you complete",
    "suggestion": "Read discovery picks to the end; finished discoveries teach this signal",
    "explicit_feedback": "Rate similar articles up (or this one) so Weirling knows you want them",
    "source_trust": "Read and rate articles from this source; trust is learned per source",
    "content_quality": "Nothing to change: this is a property of the article (length, sources, depth)",
    "temporal_context": "Nothing to change: newer articles get a small freshness boost",
    "novelty": "Nothing to change: novelty depends on how different it is from what you read lately",
}


async def explain_item(user: User, item: ContentItem, session: AsyncSession) -> dict:
    from app.services.feed_identity import equivalent_source_ids, from_user_feeds, user_feed_ids
    from app.services.ranking.ranker import _ensure_candidate_feeds, load_state, score_candidates

    state = await load_state(user, session)
    await _ensure_candidate_feeds(state, [item], session)
    scored = score_candidates(state, [item])[0]

    contributions = [
        {
            "signal": name,
            "feature": round(float(scored.features[name]), 4),
            "weight": round(float(state.weights[name]), 4),
            "contribution": round(float(scored.contributions[name]), 4),
            "has_data": name not in scored.no_data,
        }
        for name in SIGNALS
    ]
    contributions.sort(
        key=lambda row: float(scored.contributions[str(row["signal"])]), reverse=True
    )

    # Biggest weighted gaps the user can act on.
    gaps = sorted(
        (
            (state.weights[name] * (1.0 - scored.features[name]), name)
            for name in SIGNALS
            if not _RAISE[name].startswith("Nothing to change")
        ),
        reverse=True,
    )
    topic = scored.topic or (item.topic_clusters or [None])[0] or "this topic"
    raise_it = [
        {"signal": name, "how": _RAISE[name].format(topic=f"“{topic}”")}
        for gap, name in gaps[:2]
        if gap > 0.01
    ]

    # Verdict: was it shown, and if not, why not.
    shown = (
        await session.execute(
            select(Digest.generated_at, DigestItem.position, DigestItem.prs_score)
            .join(DigestItem, DigestItem.digest_id == Digest.id)
            .where(Digest.user_id == user.id, DigestItem.content_item_id == item.id)
            .order_by(Digest.generated_at.desc())
            .limit(1)
        )
    ).first()
    source_ids = await equivalent_source_ids(session, user.id)
    feed_ids = await user_feed_ids(session, user.id)
    followed = bool(
        (source_ids or feed_ids)
        and (
            await session.execute(
                select(func.count())
                .select_from(ContentItem)
                .where(ContentItem.id == item.id, from_user_feeds(source_ids, feed_ids))
            )
        ).scalar()
    )
    latest = (
        await session.execute(
            select(Digest.id, Digest.generated_at)
            .where(Digest.user_id == user.id)
            .order_by(Digest.generated_at.desc())
            .limit(1)
        )
    ).first()
    cutoff = None
    if latest is not None:
        cutoff = (
            await session.execute(
                select(func.min(DigestItem.prs_score)).where(DigestItem.digest_id == latest.id)
            )
        ).scalar()

    if shown is not None:
        verdict = "shown"
        message = f"It was in your digest on {shown.generated_at:%B %d}, at position {shown.position + 1}."
    elif not item.rankable:
        verdict = "not_an_article"
        message = "It looks like a listing or index page, not an article, so digests skip it."
    elif not followed and item.owner_user_id is None:
        verdict = "not_followed"
        message = (
            "It isn't from a source you follow, so it could only reach you as a discovery pick."
        )
    elif cutoff is not None and scored.prs < float(cutoff):
        verdict = "ranked_below_cutoff"
        message = (
            f"It scored {scored.prs:.2f}; the lowest item in your latest digest scored "
            f"{float(cutoff):.2f}, so it didn't make the cut."
        )
    elif latest is None:
        verdict = "no_digest_yet"
        message = "You don't have a digest yet; this is how it would score today."
    else:
        verdict = "outside_window"
        message = (
            "It scores well enough today, but it wasn't among the newest items when your "
            "digests were built (or it arrived after the latest one)."
        )

    return {
        "content_id": str(item.id),
        "title": item.title,
        "score": round(float(scored.prs), 4),
        "explanation": scored.explanation,
        "why_topics": scored.why_topics,
        "verdict": verdict,
        "message": message,
        "latest_digest_cutoff": round(float(cutoff), 4) if cutoff is not None else None,
        "contributions": contributions,
        "raise_it": raise_it,
    }


async def explain_item_id(user: User, content_id: uuid.UUID, session: AsyncSession) -> dict | None:
    from app.services.feed_identity import visible_item_filter

    item = (
        await session.execute(
            select(ContentItem).where(ContentItem.id == content_id, visible_item_filter(user.id))
        )
    ).scalar_one_or_none()
    if item is None:
        return None
    return await explain_item(user, item, session)
