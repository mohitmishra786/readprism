from __future__ import annotations

import asyncio
import math
from typing import Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
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

    # Compute PRS for all items concurrently (batched to avoid overwhelming DB)
    batch_size = 20
    all_results: list[Tuple[ContentItem, float, dict]] = []

    for i in range(0, len(content_items), batch_size):
        batch = content_items[i : i + batch_size]
        tasks = [compute_prs(item, user, session) for item in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for item, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                logger.warning(f"PRS computation failed for {item.id}: {result}")
                all_results.append((item, 0.0, {}))
            else:
                prs, breakdown = result
                all_results.append((item, prs, breakdown))

    # Sort by PRS descending
    all_results.sort(key=lambda x: x[1], reverse=True)

    # Mark bottom 15% as serendipity candidates (do not filter out — flag them)
    if all_results:
        threshold_idx = math.ceil(len(all_results) * 0.85)
        for idx, (item, prs, breakdown) in enumerate(all_results):
            if idx >= threshold_idx:
                breakdown["_serendipity_candidate"] = True

    return all_results[:limit]
