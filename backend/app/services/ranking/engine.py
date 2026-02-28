from __future__ import annotations

import asyncio
import math
from typing import Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.services.ranking.scorer import compute_prs
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def rank_content_for_user(
    user: User,
    content_items: list[ContentItem],
    session: AsyncSession,
    limit: int = 100,
) -> list[Tuple[ContentItem, float, dict]]:
    if not content_items:
        return []

    # Load pre-computed PRS scores from DB (written by the background precompute task)
    content_ids = [item.id for item in content_items]
    cached_result = await session.execute(
        select(UserContentInteraction).where(
            UserContentInteraction.user_id == user.id,
            UserContentInteraction.content_item_id.in_(content_ids),
            UserContentInteraction.prs_score.isnot(None),
        )
    )
    cached_map: dict = {
        ix.content_item_id: ix.prs_score
        for ix in cached_result.scalars().all()
    }

    items_needing_live_prs = [item for item in content_items if item.id not in cached_map]
    cache_hits = len(content_items) - len(items_needing_live_prs)
    if cache_hits:
        logger.debug(f"PRS cache: {cache_hits} hits, {len(items_needing_live_prs)} misses for user {user.id}")

    # For items without a cached score, compute live (batched)
    live_scores: dict = {}
    live_breakdowns: dict = {}
    batch_size = 20
    for i in range(0, len(items_needing_live_prs), batch_size):
        batch = items_needing_live_prs[i : i + batch_size]
        tasks = [compute_prs(item, user, session) for item in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for item, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                logger.warning(f"PRS live computation failed for {item.id}: {result}")
                live_scores[item.id] = 0.0
                live_breakdowns[item.id] = {}
            else:
                prs, breakdown = result
                live_scores[item.id] = prs
                live_breakdowns[item.id] = breakdown

    # Assemble final list
    all_results: list[Tuple[ContentItem, float, dict]] = []
    for item in content_items:
        if item.id in cached_map:
            all_results.append((item, cached_map[item.id], {"_cached": True}))
        else:
            all_results.append((item, live_scores.get(item.id, 0.0), live_breakdowns.get(item.id, {})))

    # Sort by PRS descending
    all_results.sort(key=lambda x: x[1], reverse=True)

    # Mark bottom 15% as serendipity candidates
    if all_results:
        threshold_idx = math.ceil(len(all_results) * 0.85)
        for idx, (item, prs, breakdown) in enumerate(all_results):
            if idx >= threshold_idx:
                breakdown["_serendipity_candidate"] = True

    return all_results[:limit]
