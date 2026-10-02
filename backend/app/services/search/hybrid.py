"""Hybrid search: Postgres FTS + pgvector, fused with Reciprocal Rank Fusion.

Postgres-only by design (D-09): FTS + vector fusion is the default; the
Meilisearch client stays dormant until this proves insufficient (UX-11 gate,
see docs/adr/0005-search-fusion.md).
"""

from __future__ import annotations

RRF_K = 60  # standard RRF constant


def rrf_fuse(
    fts_ids: list[str],
    vector_ids: list[str],
    *,
    k: int = RRF_K,
) -> list[str]:
    """Fuse two ranked id lists into one ordering.

    score(d) = sum over lists of 1 / (k + rank(d)); rank is 1-based. Items in
    both lists gain both contributions, which is exactly the hybrid behavior:
    a doc that is textually relevant AND semantically close wins.
    Ties break by first appearance (FTS list wins ties — lexical exactness).
    """
    scores: dict[str, float] = {}
    for rank, item_id in enumerate(fts_ids, start=1):
        scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    for rank, item_id in enumerate(vector_ids, start=1):
        scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    # Stable sort by (-score, first seen). Track first-seen order.
    first_seen: dict[str, int] = {}
    for index, item_id in enumerate(fts_ids + vector_ids):
        first_seen.setdefault(item_id, index)
    return sorted(scores, key=lambda item_id: (-scores[item_id], first_seen[item_id]))
