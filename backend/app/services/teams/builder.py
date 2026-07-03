"""Team digest builder.

A team digest promotes content that's broadly relevant across the team's
members. Strategy:
1. Build a merged interest vector = mean of all members' interest vectors.
2. Rank candidate items by cosine similarity to the merged vector.
3. Boost items that are shared-interest (sim high vs merged) but also surface a
   small slice from each member's personal niche, so individuals still see
   their own specialty content reflected.
"""
from __future__ import annotations

import uuid

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.team import Team, TeamMember
from app.services.interest_graph.graph import InterestGraphManager
from app.utils.logging import get_logger

logger = get_logger(__name__)
graph_manager = InterestGraphManager()

# How many items per digest, and how large a candidate pool to rank from.
TEAM_DIGEST_SIZE = 15
CANDIDATE_POOL = 200
# Fraction of the digest reserved for per-member niche items.
NICHE_SLICE_PCT = 0.3


async def _merged_interest_vector(
    member_ids: list[uuid.UUID], session: AsyncSession
) -> np.ndarray | None:
    """Mean of members' cached interest vectors. Returns None if none available."""
    vecs: list[np.ndarray] = []
    for uid in member_ids:
        vec = await graph_manager.build_user_interest_vector(uid, session)
        if vec is not None:
            vecs.append(np.array(vec, dtype=np.float32))
    if not vecs:
        return None
    merged = np.mean(np.stack(vecs), axis=0)
    norm = np.linalg.norm(merged)
    return merged / norm if norm > 0 else merged


async def build_team_digest(
    team_id: uuid.UUID, session: AsyncSession
) -> dict:
    """Build a ranked team digest.

    Returns a dict with the team id, the merged-interest summary, and a list of
    ranked items (each with prs_score and the contributing member ids). The
    caller (an API endpoint or worker task) is responsible for persistence and
    delivery.
    """
    members_result = await session.execute(
        select(TeamMember.user_id).where(TeamMember.team_id == team_id)
    )
    member_ids = [row[0] for row in members_result.fetchall()]
    if not member_ids:
        return {"team_id": str(team_id), "items": [], "reason": "no_members"}

    merged_vec = await _merged_interest_vector(member_ids, session)
    if merged_vec is None:
        return {"team_id": str(team_id), "items": [], "reason": "no_interest_data"}

    # Candidate pool: items that at least one member positively engaged with
    # (opened, saved, or rated) in the last 7 days. We scope to members'
    # interactions rather than all recent content, so the candidate set is
    # genuinely team-relevant and the join doesn't pull in unrelated items.
    from datetime import datetime, timezone, timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    candidate_result = await session.execute(
        select(ContentItem)
        .join(
            UserContentInteraction,
            UserContentInteraction.content_item_id == ContentItem.id,
        )
        .where(
            UserContentInteraction.user_id.in_(member_ids),
            UserContentInteraction.created_at >= cutoff,
            # Positive engagement: opened, saved, or explicitly rated.
            (
                UserContentInteraction.opened_at.is_not(None)
                | UserContentInteraction.saved.is_(True)
                | UserContentInteraction.explicit_rating.is_not(None)
            ),
            ContentItem.embedding.is_not(None),
        )
        .distinct()
        .limit(CANDIDATE_POOL)
    )
    candidates = list(candidate_result.scalars().all())
    if not candidates:
        return {"team_id": str(team_id), "items": [], "reason": "no_candidates"}

    # Rank by cosine similarity to the merged team vector.
    scored: list[tuple[float, ContentItem]] = []
    for item in candidates:
        if item.embedding is None:
            continue
        vec = np.array(item.embedding, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm == 0:
            continue
        sim = float(np.dot(merged_vec, vec) / (norm + 1e-8))
        scored.append((sim, item))
    scored.sort(key=lambda x: x[0], reverse=True)

    # Shared-interest slice: top items by team relevance.
    niche_count = max(1, int(TEAM_DIGEST_SIZE * NICHE_SLICE_PCT))
    shared_count = TEAM_DIGEST_SIZE - niche_count
    shared_items = scored[:shared_count]

    # Niche slice: for each member, take their single most-personally-relevant
    # item not already in the shared slice, so every member sees a reflection
    # of their own specialty.
    used_ids = {item.id for _, item in shared_items}
    niche_items: list[tuple[float, ContentItem]] = []
    for uid in member_ids:
        member_vec = await graph_manager.build_user_interest_vector(uid, session)
        if member_vec is None:
            continue
        member_vec = np.array(member_vec, dtype=np.float32)
        mnorm = np.linalg.norm(member_vec)
        if mnorm == 0:
            continue
        best: tuple[float, ContentItem] | None = None
        for _, item in scored[shared_count:]:
            if item.id in used_ids or item.embedding is None:
                continue
            vec = np.array(item.embedding, dtype=np.float32)
            vnorm = np.linalg.norm(vec)
            if vnorm == 0:
                continue
            sim = float(np.dot(member_vec, vec) / (mnorm * vnorm + 1e-8))
            if best is None or sim > best[0]:
                best = (sim, item)
        if best is not None:
            niche_items.append(best)
            used_ids.add(best[1].id)
        if len(niche_items) >= niche_count:
            break

    ranked = shared_items + niche_items
    return {
        "team_id": str(team_id),
        "items": [
            {"content_id": str(item.id), "title": item.title, "prs_score": score}
            for score, item in ranked
        ],
        "member_count": len(member_ids),
    }
