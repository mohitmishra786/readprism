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
    """
    clusters: list[list[int]] = []
    for index, item in enumerate(items):
        placed = False
        for cluster in clusters:
            seed = items[cluster[0]]
            seed_vec = getattr(seed, "embedding", None)
            item_vec = getattr(item, "embedding", None)
            similar = False
            if seed_vec is not None and item_vec is not None:
                similar = cosine(list(seed_vec), list(item_vec)) >= embed_threshold
            elif seed_vec is None and item_vec is None:
                # Title overlap is ONLY the both-without-vectors path: with
                # one vector present the comparison never happened, and a
                # false-positive cluster silently drops a distinct article
                # (CodeRabbit).
                similar = (
                    title_overlap(seed.title, item.title) >= title_threshold
                    and len(title_tokens(seed.title)) >= MIN_TITLE_TOKENS
                    and len(title_tokens(item.title)) >= MIN_TITLE_TOKENS
                )
            if similar:
                cluster.append(index)
                placed = True
                break
        if not placed:
            clusters.append([index])
    return clusters
