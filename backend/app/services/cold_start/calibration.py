"""Post-backfill calibration (CS-03).

After the first ingest, show 8-12 DIVERSE items (farthest-point spread over
embeddings) for quick thumbs; each rating immediately reinforces or
suppresses the matching interest clusters. Population-free by construction.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_K = 10


@dataclass(frozen=True)
class CalibrationPick:
    index: int
    reason: str  # "seed" | "farthest"


def _cosine(left: list[float], right: list[float]) -> float:
    import math

    num = sum(a * b for a, b in zip(left, right, strict=False))
    left_sq = math.sqrt(sum(a * a for a in left))
    right_sq = math.sqrt(sum(b * b for b in right))
    if left_sq <= 1e-8 or right_sq <= 1e-8:
        return 0.0
    return num / (left_sq * right_sq)


def select_calibration_items(
    embeddings: list[list[float] | None],
    *,
    k: int = DEFAULT_K,
) -> list[CalibrationPick]:
    """Farthest-point selection over non-null embeddings; items without
    vectors are interleaved after the spread so they can still be rated.

    Deterministic: the first embeddable candidate seeds the selection.
    """
    if not embeddings or k <= 0:
        return []

    picks: list[CalibrationPick] = []
    chosen_vecs: list[list[float]] = []

    for index, vec in enumerate(embeddings):
        if len(picks) >= k:
            break
        if vec is None:
            continue
        if not chosen_vecs:
            picks.append(CalibrationPick(index, "seed"))
            chosen_vecs.append(vec)
            continue
        # Distance to the closest already-picked item (max-min spread).
        distance = min(1.0 - _cosine(vec, other) for other in chosen_vecs)
        if distance > 0.35:
            picks.append(CalibrationPick(index, "farthest"))
            chosen_vecs.append(vec)

    # Interleave no-embedding items (recency-only) if the spread came up short.
    for index, vec in enumerate(embeddings):
        if len(picks) >= k:
            break
        if vec is None and all(p.index != index for p in picks):
            picks.append(CalibrationPick(index, "recency"))
    return picks
