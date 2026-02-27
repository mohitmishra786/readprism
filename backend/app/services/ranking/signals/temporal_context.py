from __future__ import annotations

from datetime import datetime, timezone, timedelta

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.services.ranking.signals import UserInterestGraph
from app.utils.logging import get_logger

logger = get_logger(__name__)

SIMILARITY_SATURATION_THRESHOLD = 0.80
SATURATION_PENALTY_PER_ITEM = 0.15
MAX_SATURATION_PENALTY = 0.60


async def compute(
    content: ContentItem,
    user: User,
    interaction_history: list[UserContentInteraction],
    interest_graph: UserInterestGraph,
    session: AsyncSession,
) -> float:
    long_term = await _long_term_score(content, interest_graph)
    medium_term = await _medium_term_score(content, user, session)
    short_term = await _short_term_adjustment(content, user, session)

    temporal_score = long_term * 0.5 + medium_term * 0.35 + short_term * 0.15
    tod_adjustment = _time_of_day_adjustment(content, interaction_history)
    return float(np.clip(temporal_score + tod_adjustment, 0.0, 1.0))


async def _long_term_score(content: ContentItem, graph: UserInterestGraph) -> float:
    if content.embedding is None:
        return 0.5
    core_nodes = [n for n in graph.nodes if n.is_core and n.topic_embedding is not None]
    if not core_nodes:
        return 0.5
    content_vec = np.array(content.embedding, dtype=np.float32)
    sims = []
    for node in core_nodes:
        node_vec = np.array(node.topic_embedding, dtype=np.float32)
        sim = float(np.dot(content_vec, node_vec) / (np.linalg.norm(content_vec) * np.linalg.norm(node_vec) + 1e-8))
        sims.append((sim + 1.0) / 2.0)
    return float(np.mean(sims)) if sims else 0.5


async def _medium_term_score(
    content: ContentItem, user: User, session: AsyncSession
) -> float:
    if content.embedding is None:
        return 0.5
    cutoff = datetime.now(timezone.utc) - timedelta(days=28)
    try:
        result = await session.execute(
            text("""
                SELECT ci.embedding
                FROM content_items ci
                JOIN user_content_interactions uci ON ci.id = uci.content_item_id
                WHERE uci.user_id = :user_id
                  AND uci.created_at >= :cutoff
                  AND ci.embedding IS NOT NULL
                LIMIT 50
            """),
            {"user_id": str(user.id), "cutoff": cutoff},
        )
        rows = result.fetchall()
        if not rows:
            return 0.5
        embeddings = np.array([row[0] for row in rows], dtype=np.float32)
        medium_vec = embeddings.mean(axis=0)
        norm = np.linalg.norm(medium_vec)
        if norm > 0:
            medium_vec = medium_vec / norm
        content_vec = np.array(content.embedding, dtype=np.float32)
        sim = float(np.dot(content_vec, medium_vec) / (np.linalg.norm(content_vec) * norm + 1e-8))
        return (sim + 1.0) / 2.0
    except Exception as e:
        logger.warning(f"medium_term_score query failed: {e}")
        return 0.5


async def _short_term_adjustment(
    content: ContentItem, user: User, session: AsyncSession
) -> float:
    if content.embedding is None:
        return 1.0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
    try:
        result = await session.execute(
            text("""
                SELECT ci.embedding
                FROM content_items ci
                JOIN user_content_interactions uci ON ci.id = uci.content_item_id
                WHERE uci.user_id = :user_id
                  AND uci.created_at >= :cutoff
                  AND ci.id != :content_id
                  AND ci.embedding IS NOT NULL
            """),
            {"user_id": str(user.id), "cutoff": cutoff, "content_id": str(content.id)},
        )
        rows = result.fetchall()
        content_vec = np.array(content.embedding, dtype=np.float32)
        seen_count = 0
        for row in rows:
            emb = np.array(row[0], dtype=np.float32)
            sim = float(np.dot(content_vec, emb) / (np.linalg.norm(content_vec) * np.linalg.norm(emb) + 1e-8))
            if (sim + 1.0) / 2.0 > SIMILARITY_SATURATION_THRESHOLD:
                seen_count += 1
        penalty = min(MAX_SATURATION_PENALTY, seen_count * SATURATION_PENALTY_PER_ITEM)
        return 1.0 - penalty
    except Exception as e:
        logger.warning(f"short_term_adjustment query failed: {e}")
        return 1.0


def _time_of_day_adjustment(
    content: ContentItem, interaction_history: list[UserContentInteraction]
) -> float:
    """
    Learn per-user time-of-day reading length preferences from opened_at history.
    Computes the median reading_time_minutes for articles opened in the current 3-hour
    window; if the candidate's length is within 50% of that median, award +0.05.
    Falls back to a static heuristic when fewer than 5 data points exist.
    """
    now_hour = datetime.now(timezone.utc).hour
    window_start = (now_hour // 3) * 3  # 0, 3, 6, 9, 12, 15, 18, 21

    # Gather reading times from history items opened in the same 3-hour window
    lengths: list[int] = []
    for ix in interaction_history:
        if ix.opened_at is None:
            continue
        opened_hour = ix.opened_at.astimezone(timezone.utc).hour
        if (opened_hour // 3) * 3 == window_start:
            lengths.append(ix.time_on_page_seconds or 0)

    if len(lengths) >= 5 and content.reading_time_minutes is not None:
        # Convert seconds to minutes
        median_minutes = sorted(lengths)[len(lengths) // 2] / 60.0
        candidate_minutes = float(content.reading_time_minutes)
        # Match if within 50% of the learned median
        if median_minutes > 0 and 0.5 <= candidate_minutes / median_minutes <= 1.5:
            return 0.05
        return 0.0

    # Static fallback: morning prefers shorter reads, evening longer
    is_morning = now_hour < 12
    if is_morning and content.reading_time_minutes is not None and content.reading_time_minutes < 8:
        return 0.05
    if not is_morning and content.reading_time_minutes is not None and content.reading_time_minutes > 10:
        return 0.05
    return 0.0
