"""The ranker: adapter connecting database state to weirling-rank (#129, #245).

Loads user state (weights, reading history with embeddings, interest graph,
per-feed outcomes) from PostgreSQL/pgvector and delegates the vectorized
scoring and ranking pass to `weirling_rank`.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.content import ContentItem, UserContentInteraction
from app.models.interest_graph import InterestEdge, InterestNode
from app.models.source import Source
from app.models.user import User
from weirling_rank import (
    CLUSTER_DISTANCE,
    KNN,
    MAX_INTEREST_VECTORS,
    NEUTRAL,
    NOVELTY_WINDOW_DAYS,
    RECENT_EVENT_HOURS,
    SAME_EVENT_COSINE,
    SIGNALS,
    BetaTrust,
    Candidate,
    FeedState,
    HistoryRow,
    Interest,
    Scored,
    UserRankingState,
    average_linkage,
    beta_trust,
    build_interests,
    clamp01,
    length_bucket,
    temporal_score,
)
from weirling_rank import score_candidates as rank_engine_score

HISTORY_LIMIT = 500
BRIDGE_EDGE_WEIGHT = 0.5

__all__ = [
    "BRIDGE_EDGE_WEIGHT",
    "CLUSTER_DISTANCE",
    "HISTORY_LIMIT",
    "KNN",
    "MAX_INTEREST_VECTORS",
    "NEUTRAL",
    "NOVELTY_WINDOW_DAYS",
    "RECENT_EVENT_HOURS",
    "SAME_EVENT_COSINE",
    "SIGNALS",
    "BetaTrust",
    "Candidate",
    "FeedState",
    "HistoryRow",
    "Interest",
    "Scored",
    "UserRankingState",
    "average_linkage",
    "beta_trust",
    "build_interests",
    "clamp01",
    "length_bucket",
    "load_state",
    "rank",
    "score_candidates",
    "temporal_score",
]


def _vec(raw) -> np.ndarray | None:
    if raw is None:
        return None
    v = np.asarray(raw, dtype=np.float32)
    norm = float(np.linalg.norm(v))
    if not math.isfinite(norm) or norm < 1e-8:
        return None
    return v / norm


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _feed_key(source: Source) -> str:
    return source.feed_url or source.url


def _is_success(row: HistoryRow) -> bool:
    return bool(
        (row.rating is not None and row.rating > 0)
        or row.saved
        or (row.completion is not None and row.completion >= 0.6)
    )


def _is_failure(row: HistoryRow) -> bool:
    return bool(
        (row.rating is not None and row.rating < 0)
        or (row.completion is not None and row.completion < 0.2 and row.opened_at is not None)
        or (row.skipped and row.opened_at is not None)
    )


async def load_state(user: User, session: AsyncSession) -> UserRankingState:
    from app.services.ranking.meta_weights import get_meta_weights

    now = datetime.now(UTC)
    meta = await get_meta_weights(user.id, session)
    weights = {name: float(meta.weights.get(name, 0.0)) for name in SIGNALS}
    total = sum(weights.values()) or 1.0
    weights = {k: v / total for k, v in weights.items()}

    rows = (
        await session.execute(
            select(UserContentInteraction, ContentItem)
            .join(ContentItem, ContentItem.id == UserContentInteraction.content_item_id)
            .where(UserContentInteraction.user_id == user.id)
            .order_by(UserContentInteraction.updated_at.desc())
            .limit(HISTORY_LIMIT)
        )
    ).all()

    own_sources = list(
        (await session.execute(select(Source).where(Source.user_id == user.id))).scalars()
    )
    feeds = {
        _feed_key(s): FeedState(name=s.name or s.url, trust_weight=float(s.trust_weight or 0.5))
        for s in own_sources
    }
    source_ids = {c.source_id for _, c in rows if c.source_id}
    source_feed_key = {s.id: _feed_key(s) for s in own_sources}
    missing = source_ids - set(source_feed_key)
    if missing:
        for s in (await session.execute(select(Source).where(Source.id.in_(missing)))).scalars():
            source_feed_key[s.id] = _feed_key(s)

    from app.services.embeddings.registry import active_spec, same_model

    settings = get_settings()
    active = active_spec(
        model=settings.embedding_model,
        cutover=settings.embedding_cutover_enabled,
    )
    history = [
        HistoryRow(
            content_id=c.id,
            vector=_vec(getattr(c, "embedding", None))
            if same_model(
                getattr(c, "embedding_model", None), getattr(c, "embedding_dim", None), active
            )
            else None,
            feed_key=source_feed_key.get(c.source_id) if c.source_id else None,
            words=int(c.word_count or 0),
            completion=ix.read_completion_pct,
            rating=ix.explicit_rating,
            reason=ix.explicit_rating_reason,
            saved=bool(ix.saved),
            skipped=bool(ix.skipped),
            was_suggested=bool(ix.was_suggested),
            opened_at=_aware(ix.opened_at),
            created_at=_aware(ix.created_at) or now,
            published_at=_aware(c.published_at) or _aware(c.fetched_at),
            title=c.title or "",
        )
        for ix, c in rows
    ]

    for row in history:
        if row.feed_key in feeds:
            feed = feeds[row.feed_key]
            if _is_success(row):
                feed.successes += 1
            elif _is_failure(row):
                feed.failures += 1
            else:
                continue
            moment = row.opened_at or row.created_at
            if feed.last_outcome_at is None or moment > feed.last_outcome_at:
                feed.last_outcome_at = moment

    nodes = list(
        (
            await session.execute(
                select(InterestNode).where(
                    InterestNode.user_id == user.id,
                    or_(
                        InterestNode.suppressed_until.is_(None),
                        InterestNode.suppressed_until <= now,
                    ),
                )
            )
        ).scalars()
    )
    edges = list(
        (
            await session.execute(select(InterestEdge).where(InterestEdge.user_id == user.id))
        ).scalars()
    )
    interest_candidates: list[tuple[np.ndarray, float, str]] = []
    node_vec: dict[uuid.UUID, tuple[np.ndarray, str]] = {}
    for node in nodes:
        # Topic vectors from another model aren't comparable (#244); they
        # come back after the re-embed task re-encodes them.
        if not same_model(getattr(node, "embedding_model", None), None, active):
            continue
        v = _vec(node.topic_embedding)
        if v is not None and (node.weight or 0) > 0:
            interest_candidates.append((v, float(node.weight), node.topic_label))
            node_vec[node.id] = (v, node.topic_label)
    for row in history:
        if row.vector is not None and _is_success(row):
            strength = 1.0 if (row.rating or 0) > 0 or row.saved else 0.7
            interest_candidates.append((row.vector, 0.5 * strength, ""))
    interests = build_interests(interest_candidates)

    bridges: list[tuple[np.ndarray, str, str]] = []
    for edge in edges:
        if (edge.edge_weight or 0) < BRIDGE_EDGE_WEIGHT:
            continue
        a, b = node_vec.get(edge.from_node_id), node_vec.get(edge.to_node_id)
        if a and b:
            mid = _vec(a[0] + b[0])
            if mid is not None:
                bridges.append((mid, a[1], b[1]))

    ages = [
        (row.opened_at - row.published_at).total_seconds() / 3600
        for row in history
        if row.opened_at and row.published_at and row.opened_at >= row.published_at
    ]
    prefers_fresh = True if len(ages) < 5 else float(np.median(ages)) < 36

    return UserRankingState(
        user_id=user.id,
        weights=weights,
        history=history,
        interests=interests,
        bridges=bridges,
        feeds=feeds,
        source_feed_key=source_feed_key,
        prefers_fresh=prefers_fresh,
        novelty_target=float(get_settings().novelty_target),
        now=now,
        feed_id_key={s.feed_id: _feed_key(s) for s in own_sources if s.feed_id is not None},
    )


async def _ensure_candidate_feeds(
    state: UserRankingState, candidates: list[ContentItem], session: AsyncSession
) -> None:
    missing = {c.source_id for c in candidates if c.source_id} - set(state.source_feed_key)
    if missing:
        for s in (await session.execute(select(Source).where(Source.id.in_(missing)))).scalars():
            state.source_feed_key[s.id] = _feed_key(s)


def score_candidates(state: UserRankingState, candidates: list[ContentItem]) -> list[Scored]:
    """Adapter delegating candidate scoring to weirling_rank (#129, #245)."""
    if not candidates:
        return []
    from app.services.embeddings.registry import active_spec, same_model

    settings = get_settings()
    active = active_spec(
        model=settings.embedding_model,
        cutover=settings.embedding_cutover_enabled,
    )
    return rank_engine_score(
        state,
        candidates,
        is_same_model=lambda model, dim: same_model(model, dim, active),
    )


async def rank(
    user: User,
    candidates: list[ContentItem],
    session: AsyncSession,
    *,
    state: UserRankingState | None = None,
) -> list[Scored]:
    """Score `candidates` for `user`, best first."""
    if not candidates:
        return []
    state = state or await load_state(user, session)
    await _ensure_candidate_feeds(state, candidates, session)
    scored = score_candidates(state, candidates)
    scored.sort(key=lambda s: s.prs, reverse=True)
    return scored
