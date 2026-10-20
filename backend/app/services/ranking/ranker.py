"""The ranker: one vectorized scoring pass over a digest's candidates (#129).

Replaces the per-item signal modules. The user's state (weights, reading
history with embeddings, interest graph, per-feed outcomes) is loaded once in
a few batched queries; the eight pre-consumption features are then computed
for every candidate with numpy and combined linearly, so every score has an
exact per-signal decomposition.

Feature definitions (all in [0, 1], all computable before the user sees the
item, never using the candidate's own interaction):

- semantic: max importance-weighted cosine to the user's interest medoids
  (interest-graph topics plus items they read or liked), or to the midpoint
  of two strongly connected topics (a "bridge") (#155, D-05);
- reading_depth: similarity-weighted completion of the most similar items
  the user opened, shrunk toward 0.5 when evidence is thin;
- suggestion: for discovery items, how often the user finished discovery
  picks (Beta-shrunk); otherwise no data;
- explicit_feedback: closeness to items rated up minus closeness to items
  rated down, plus reason-tag penalties;
- source_trust: Beta posterior of the user's outcomes on this feed, with the
  user's own trust weight as the prior mean (#108: per-user, per-feed);
- content_quality: length / citations / depth heuristic, shrunk toward the
  user's completion for that length bucket;
- temporal_context: long/medium/fresh age blend with a same-event
  saturation penalty;
- novelty: distance from the last 30 days of reading, peaking at the target.

A feature with no evidence for this user/item is held at a neutral 0.5 and
reported in `no_data` (#135): it shifts every score equally, so it neither
helps nor hurts the ranking, the pairwise learner gets no gradient from it,
and explanations never cite it (#143).
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.interest_graph import InterestEdge, InterestNode
from app.models.source import Source
from app.models.user import User
from app.services.ranking.contract import (
    SIGNALS,
    beta_trust,
    clamp01,
    length_bucket,
    temporal_score,
)

NEUTRAL = 0.5
HISTORY_LIMIT = 500
MAX_INTEREST_VECTORS = 80
CLUSTER_DISTANCE = 0.45
BRIDGE_EDGE_WEIGHT = 0.5
KNN = 15
SAME_EVENT_COSINE = 0.85
NOVELTY_WINDOW_DAYS = 30
RECENT_EVENT_HOURS = 72


# --------------------------------------------------------------------- state


@dataclass
class HistoryRow:
    content_id: uuid.UUID
    vector: np.ndarray | None
    feed_key: str | None
    words: int
    completion: float | None
    rating: int | None
    reason: str | None
    saved: bool
    skipped: bool
    was_suggested: bool
    opened_at: datetime | None
    created_at: datetime
    published_at: datetime | None
    title: str


@dataclass
class Interest:
    vector: np.ndarray
    importance: float
    label: str


@dataclass
class FeedState:
    name: str
    trust_weight: float
    successes: float = 0.0
    failures: float = 0.0
    last_outcome_at: datetime | None = None


@dataclass
class UserRankingState:
    user_id: uuid.UUID
    weights: dict[str, float]
    history: list[HistoryRow]
    interests: list[Interest]
    bridges: list[tuple[np.ndarray, str, str]]
    feeds: dict[str, FeedState]
    source_feed_key: dict[uuid.UUID, str]
    prefers_fresh: bool
    novelty_target: float
    now: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Shared feed id -> the user's own feed key (#161), for items whose
    # filing source row was deleted.
    feed_id_key: dict[uuid.UUID, str] = field(default_factory=dict)


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


def average_linkage(vectors: np.ndarray, threshold: float) -> list[list[int]]:
    """Agglomerative clustering, average linkage on cosine distance.

    Lance-Williams updates on an n x n distance matrix: O(n^2) per merge,
    fast for the <= 80 interest vectors a user has.
    """
    n = len(vectors)
    if n == 0:
        return []
    dist = 1.0 - np.clip(vectors @ vectors.T, -1.0, 1.0)
    np.fill_diagonal(dist, np.inf)
    sizes = np.ones(n)
    members: dict[int, list[int]] = {i: [i] for i in range(n)}
    active = np.ones(n, dtype=bool)
    while active.sum() > 1:
        masked = np.where(np.outer(active, active), dist, np.inf)
        flat = int(np.argmin(masked))
        i, j = divmod(flat, n)
        if not math.isfinite(masked[i, j]) or masked[i, j] > threshold:
            break
        if i > j:
            i, j = j, i
        merged = (sizes[i] * dist[i] + sizes[j] * dist[j]) / (sizes[i] + sizes[j])
        dist[i, :] = merged
        dist[:, i] = merged
        dist[i, i] = np.inf
        dist[j, :] = np.inf
        dist[:, j] = np.inf
        sizes[i] += sizes[j]
        members[i].extend(members.pop(j))
        active[j] = False
    return [members[i] for i in range(n) if active[i]]


def build_interests(
    candidates: list[tuple[np.ndarray, float, str]],
) -> list[Interest]:
    """Cluster interest vectors and keep one medoid per cluster (D-05)."""
    if not candidates:
        return []
    candidates = sorted(candidates, key=lambda c: c[1], reverse=True)[:MAX_INTEREST_VECTORS]
    matrix = np.stack([c[0] for c in candidates])
    interests: list[Interest] = []
    for group in average_linkage(matrix, CLUSTER_DISTANCE):
        sub = matrix[group]
        centroid = sub.mean(axis=0)
        medoid = group[int(np.argmax(sub @ centroid))]
        importance = float(sum(candidates[i][1] for i in group))
        labels = [candidates[i][2] for i in group if candidates[i][2]]
        label = max(set(labels), key=labels.count) if labels else ""
        interests.append(Interest(matrix[medoid], importance, label))
    interests.sort(key=lambda it: it.importance, reverse=True)
    return interests


async def load_state(user: User, session: AsyncSession) -> UserRankingState:
    from app.config import get_settings
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

    history = [
        HistoryRow(
            content_id=c.id,
            vector=_vec(getattr(c, "embedding", None)),
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


# ------------------------------------------------------------------ features


@dataclass
class Scored:
    item: ContentItem
    prs: float
    features: dict[str, float]
    no_data: list[str]
    contributions: dict[str, float]
    explanation: str
    why_topics: str | None
    topic: str | None
    vector: np.ndarray | None

    def breakdown(self) -> dict:
        out: dict = {name: round(self.features[name], 6) for name in SIGNALS}
        out["contributions"] = self.contributions
        out["no_data"] = self.no_data
        out["explanation"] = self.explanation
        if self.why_topics:
            out["why_topics"] = self.why_topics
        return out


async def _ensure_candidate_feeds(
    state: UserRankingState, candidates: list[ContentItem], session: AsyncSession
) -> None:
    missing = {c.source_id for c in candidates if c.source_id} - set(state.source_feed_key)
    if missing:
        for s in (await session.execute(select(Source).where(Source.id.in_(missing)))).scalars():
            state.source_feed_key[s.id] = _feed_key(s)


def _quality(item: ContentItem, bucket_completion: float | None) -> float:
    words = int(item.word_count or 0)
    length = 0.2 if words < 200 else 0.7 if words < 2000 else 0.85
    density = 0.6 if item.has_citations else 0.2
    depth = float(item.content_depth_score) if item.content_depth_score is not None else 0.5
    original = 0.1 if item.is_original_reporting else 0.0
    raw = clamp01(0.45 * length + 0.2 * density + 0.25 * depth + original)
    if bucket_completion is None:
        return raw
    return clamp01(0.7 * raw + 0.3 * bucket_completion)


def score_candidates(state: UserRankingState, candidates: list[ContentItem]) -> list[Scored]:
    """Pure: features, scores and explanations for every candidate."""
    if not candidates:
        return []
    now = state.now
    vecs = [_vec(getattr(c, "embedding", None)) for c in candidates]
    dim = next((v.shape[0] for v in vecs if v is not None), None)

    hist = state.history
    hist_vec_rows = [r for r in hist if r.vector is not None and dim and r.vector.shape[0] == dim]
    H = np.stack([r.vector for r in hist_vec_rows]) if hist_vec_rows else None
    hist_ids = [r.content_id for r in hist_vec_rows]

    completions = (
        np.array([r.completion if r.completion is not None else np.nan for r in hist_vec_rows])
        if hist_vec_rows
        else np.array([])
    )
    ratings = np.array([r.rating or 0 for r in hist_vec_rows]) if hist_vec_rows else np.array([])
    recent_cut = now - timedelta(days=NOVELTY_WINDOW_DAYS)
    recent_mask = (
        np.array(
            [
                (r.opened_at or r.created_at) >= recent_cut and r.opened_at is not None
                for r in hist_vec_rows
            ]
        )
        if hist_vec_rows
        else np.array([], dtype=bool)
    )
    event_cut = now - timedelta(hours=RECENT_EVENT_HOURS)
    event_mask = (
        np.array([r.opened_at is not None and r.opened_at >= event_cut for r in hist_vec_rows])
        if hist_vec_rows
        else np.array([], dtype=bool)
    )

    # Length-bucket completion, for quality shrinkage.
    bucket_vals: dict[str, list[float]] = {}
    for r in hist:
        if r.completion is not None and r.opened_at is not None:
            bucket_vals.setdefault(length_bucket(r.words), []).append(float(r.completion))
    bucket_completion = {k: float(np.mean(v)) for k, v in bucket_vals.items() if len(v) >= 3}

    suggested = [r for r in hist if r.was_suggested and r.opened_at is not None]
    sugg_success = sum(1 for r in suggested if _is_success(r))

    interest_matrix = np.stack([it.vector for it in state.interests]) if state.interests else None
    interest_imp = np.array([it.importance for it in state.interests]) if state.interests else None
    bridge_matrix = np.stack([b[0] for b in state.bridges]) if state.bridges else None

    cand_matrix_rows = [i for i, v in enumerate(vecs) if v is not None and v.shape[0] == dim]
    C = np.stack([vecs[i] for i in cand_matrix_rows]) if cand_matrix_rows else None
    cand_sim = C @ C.T if C is not None else None
    cand_pos = {i: k for k, i in enumerate(cand_matrix_rows)}

    results: list[Scored] = []
    for idx, item in enumerate(candidates):
        f: dict[str, float] = {name: NEUTRAL for name in SIGNALS}
        have: set[str] = set()
        notes: dict[str, str] = {}
        v = vecs[idx] if idx in cand_pos else None
        topic: str | None = (item.topic_clusters or [None])[0]
        why_topics: str | None = None

        # Leakage guard: never use the candidate's own history row.
        keep = np.array([cid != item.id for cid in hist_ids], dtype=bool) if hist_ids else None
        sims = (H @ v) if (H is not None and v is not None) else None

        # semantic
        if (
            v is not None
            and interest_matrix is not None
            and interest_imp is not None
            and interest_matrix.shape[1] == v.shape[0]
        ):
            top = min(3, len(state.interests))
            cos = np.clip(interest_matrix[:top] @ v, 0.0, 1.0)
            weighted = cos * (interest_imp[:top] / max(interest_imp[:top].max(), 1e-8))
            best = int(np.argmax(weighted))
            score = float(weighted[best])
            label = state.interests[best].label
            if bridge_matrix is not None and bridge_matrix.shape[1] == v.shape[0]:
                bcos = np.clip(bridge_matrix @ v, 0.0, 1.0)
                bbest = int(np.argmax(bcos))
                if bcos[bbest] > score + 0.02:
                    score = float(bcos[bbest])
                    _, a, b = state.bridges[bbest]
                    why_topics = f"connects your interest in {a} and {b}"
                    topic = topic or a
            if why_topics is None and label:
                why_topics = f"matches your interest in {label}"
                topic = topic or label
            f["semantic"] = clamp01(score)
            have.add("semantic")

        # reading depth (kNN over opened items with completion)
        if sims is not None and keep is not None:
            mask = keep & ~np.isnan(completions)
            if mask.sum() >= 3:
                s = np.where(mask, np.clip(sims, 0.0, 1.0), -1.0)
                order = np.argsort(-s)[:KNN]
                order = order[s[order] > 0]
                if len(order):
                    w = s[order]
                    mean = float(np.dot(w, completions[order]) / (w.sum() + 1e-8))
                    shrink = w.sum() / (w.sum() + 2.0)
                    f["reading_depth"] = clamp01(shrink * mean + (1 - shrink) * NEUTRAL)
                    have.add("reading_depth")
                    notes["reading_depth"] = f"{round(mean * 100)}%"

        # suggestion
        if getattr(item, "origin", None) == "discovery":
            f["suggestion"] = clamp01((2.0 + sugg_success) / (3.0 + len(suggested)))
            have.add("suggestion")
            if sugg_success > 0:
                notes["suggestion"] = "a discovery pick like ones you finished before"

        # explicit feedback
        if sims is not None and keep is not None:
            pos = keep & (ratings > 0)
            neg = keep & (ratings < 0)
            if pos.any() or neg.any():
                p = float(np.clip(sims[pos], 0, 1).max()) if pos.any() else 0.0
                n = float(np.clip(sims[neg], 0, 1).max()) if neg.any() else 0.0
                value = 0.5 + 0.5 * p - 0.5 * n
                reasons = {r.reason for r in hist if r.rating is not None and r.rating < 0}
                if (
                    "too_basic" in reasons
                    and item.content_depth_score is not None
                    and item.content_depth_score < 0.4
                ):
                    value -= 0.1
                f["explicit_feedback"] = clamp01(value)
                have.add("explicit_feedback")
                if p >= n and p > 0.5:
                    notes["explicit_feedback"] = "similar to articles you rated up"

        # source trust (per user, per feed)
        key = state.source_feed_key.get(item.source_id) if item.source_id else None
        if key is None and item.feed_id is not None:
            key = state.feed_id_key.get(item.feed_id)
        feed = state.feeds.get(key) if key else None
        if feed is not None:
            age = (now - feed.last_outcome_at).days if feed.last_outcome_at else 0.0
            prior_mean = clamp01(feed.trust_weight)
            trust = beta_trust(
                feed.successes,
                feed.failures,
                prior_success=4.0 * prior_mean,
                prior_failure=4.0 * (1.0 - prior_mean),
                age_days=age,
            )
            outcomes = feed.successes + feed.failures
            if outcomes > 0 or abs(feed.trust_weight - 0.5) > 0.06:
                f["source_trust"] = trust.mean
                have.add("source_trust")
                if outcomes >= 3:
                    rate = feed.successes / outcomes
                    notes["source_trust"] = (
                        f"from {feed.name}, which you finish {round(rate * 100)}% of the time"
                    )
                else:
                    notes["source_trust"] = f"from {feed.name}"

        # content quality (always available)
        bucket = length_bucket(item.word_count)
        f["content_quality"] = _quality(item, bucket_completion.get(bucket))
        have.add("content_quality")
        if (item.reading_time_minutes or 0) >= 8:
            notes["content_quality"] = f"an in-depth {item.reading_time_minutes}-minute read"

        # temporal context (always available)
        published = _aware(item.published_at) or _aware(item.fetched_at) or now
        same_event = 1
        if idx in cand_pos and cand_sim is not None:
            same_event += int((cand_sim[cand_pos[idx]] >= SAME_EVENT_COSINE).sum()) - 1
        if sims is not None and event_mask.size:
            same_event += int(((sims >= SAME_EVENT_COSINE) & event_mask).sum())
        f["temporal_context"] = temporal_score(
            published_at=published,
            now=now,
            same_event_count=same_event,
            user_prefers_fresh=state.prefers_fresh,
        )
        have.add("temporal_context")
        hours = max(0.0, (now - published).total_seconds() / 3600)
        if hours <= 24:
            notes["temporal_context"] = "published in the last day"

        # novelty
        if sims is not None and keep is not None and recent_mask.size:
            mask = keep & recent_mask
            if mask.sum() >= 3:
                nearest = float(np.clip(sims[mask], 0, 1).max())
                novelty = 1.0 - nearest
                target = state.novelty_target or 0.35
                f["novelty"] = clamp01(1.0 - abs(novelty - target) / target)
                have.add("novelty")
                if novelty >= target:
                    notes["novelty"] = "a fresh angle compared with your recent reading"

        prs = float(sum(state.weights[name] * f[name] for name in SIGNALS))
        contributions = {name: state.weights[name] * f[name] for name in SIGNALS}
        no_data = [name for name in SIGNALS if name not in have]
        explanation = _explain(contributions, have, notes, why_topics)
        results.append(
            Scored(
                item=item,
                prs=clamp01(prs),
                features=f,
                no_data=no_data,
                contributions=contributions,
                explanation=explanation,
                why_topics=why_topics,
                topic=topic,
                vector=v,
            )
        )
    return results


_PHRASES = {
    "semantic": None,  # uses why_topics
    "reading_depth": "you usually finish articles like this",
    "suggestion": "a discovery pick",
    # Claims about this item: said only when the signal's note backs them
    # (#321). A bare fallback made every item "similar to articles you rated
    # up" whenever the signal merely had data.
    "explicit_feedback": None,
    "source_trust": "from a source you read",
    "content_quality": "a substantial read",
    "temporal_context": "timely",
    "novelty": None,
}


def _explain(
    contributions: dict[str, float], have: set[str], notes: dict[str, str], why_topics: str | None
) -> str:
    """Name the one or two strongest signals that actually had evidence (#143)."""
    learned = [name for name in have if name not in ("content_quality", "temporal_context")]
    if not learned:
        return "New to ReadPrism: ranked by freshness and depth while it learns what you read"
    ordered = sorted(have, key=lambda name: contributions[name], reverse=True)
    parts: list[str] = []
    for name in ordered:
        phrase: str | None
        if name == "semantic" and why_topics:
            phrase = why_topics
        elif name == "reading_depth" and name in notes:
            phrase = f"you finish about {notes[name]} of similar articles"
        else:
            phrase = notes.get(name) or _PHRASES.get(name)
        if phrase and phrase not in parts:
            parts.append(phrase)
        if len(parts) == 2:
            break
    text = " · ".join(parts)
    return text[:1].upper() + text[1:]


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
