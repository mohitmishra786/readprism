"""Cross-source story clustering (UX-09).

Same-story detection within the digest window:
- embedding pairs at cosine >= EMBED_THRESHOLD, or
- title token overlap (Jaccard >= TITLE_THRESHOLD) as the no-embedding path.

The kept "primary" item becomes one digest card that carries the other
sources as `perspectives` (title + url + source), so one story reads as
N attributed viewpoints instead of N near-duplicate cards. The LLM briefing
is cached; without one, the perspectives list IS the fallback rendering.
"""

from __future__ import annotations

from dataclasses import dataclass

EMBED_THRESHOLD = 0.88
TITLE_THRESHOLD = 0.6
# Titles with fewer significant tokens than this cannot claim a story match:
# "Apple earnings" vs "Apple earnings call" is not the same story.
MIN_TITLE_TOKENS = 3


@dataclass(frozen=True)
class Perspective:
    title: str
    url: str
    source_id: str | None


def title_tokens(title: str) -> set[str]:
    """Lowercase significant tokens (>=3 chars, not stopwords)."""
    stop = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "into",
        "your",
        "how",
        "why",
        "what",
        "a",
        "an",
        "in",
        "on",
        "of",
        "to",
        "is",
        "are",
        "it",
        "at",
        "by",
    }
    return {t for t in title.lower().split() if len(t) >= 3 and t not in stop}


def title_overlap(left: str, right: str) -> float:
    left_tokens, right_tokens = title_tokens(left), title_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    inter = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return inter / union


def cosine(left: list[float], right: list[float]) -> float:
    left_sq = sum(v * v for v in left) ** 0.5
    right_sq = sum(v * v for v in right) ** 0.5
    if left_sq <= 1e-8 or right_sq <= 1e-8:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=False)) / (left_sq * right_sq)


def cluster_stories(
    items: list,
    *,
    embed_threshold: float = EMBED_THRESHOLD,
    title_threshold: float = TITLE_THRESHOLD,
) -> list[list[int]]:
    """Greedy clustering: first-encountered item seeds a story; every later
    item joins the first story it is similar to (embedding if both have
    vectors, else title overlap). Returns indexes into `items`.

    Vectorised (#313): the embedding comparison against every story seed is
    one matrix product instead of a pure-Python cosine per pair, which took
    ~12 s per digest build at 1,000 candidates. Same result as comparing
    seeds one by one in story order.
    """
    import numpy as np

    vectors: list = []
    dim = None
    for item in items:
        raw = getattr(item, "embedding", None)
        if raw is None:
            vectors.append(None)
            continue
        vec = np.asarray(raw, dtype=np.float64)
        norm = float(np.linalg.norm(vec))
        # A zero vector still counts as "has a vector" (no title fallback)
        # but can never reach the threshold, as before.
        vectors.append(vec / norm if norm > 1e-8 else np.zeros_like(vec))
        dim = dim or vec.shape[0]

    clusters: list[list[int]] = []
    # Story seeds that have vectors: one row each, in story order.
    seed_rows = np.zeros((len(items), dim or 1), dtype=np.float64)
    seed_clusters: list[int] = []  # cluster index of each seed row
    text_seeds: list[int] = []  # cluster indexes whose seed has no vector

    for index, item in enumerate(items):
        vec = vectors[index]
        target = None
        if vec is not None:
            # Only vector seeds can match a vector item.
            if seed_clusters and vec.shape[0] == seed_rows.shape[1]:
                sims = seed_rows[: len(seed_clusters)] @ vec
                hits = np.nonzero(sims >= embed_threshold)[0]
                if hits.size:
                    target = seed_clusters[int(hits[0])]
        else:
            # Title overlap is ONLY the both-without-vectors path: with one
            # vector present the comparison never happened, and a
            # false-positive cluster silently drops a distinct article
            # (CodeRabbit).
            for cluster_index in text_seeds:
                seed = items[clusters[cluster_index][0]]
                if (
                    title_overlap(seed.title, item.title) >= title_threshold
                    and len(title_tokens(seed.title)) >= MIN_TITLE_TOKENS
                    and len(title_tokens(item.title)) >= MIN_TITLE_TOKENS
                ):
                    target = cluster_index
                    break
        if target is not None:
            clusters[target].append(index)
            continue
        clusters.append([index])
        if vec is not None and vec.shape[0] == seed_rows.shape[1]:
            seed_rows[len(seed_clusters)] = vec
            seed_clusters.append(len(clusters) - 1)
        elif vec is None:
            text_seeds.append(len(clusters) - 1)
    return clusters
