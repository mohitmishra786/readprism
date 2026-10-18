"""Interest clustering helpers for ranking: diversity re-rank and outbound links.

Diversity is MMR plus a cluster cap; both stay pure so the eval harness can
run offline.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from urllib.parse import urlparse

import numpy as np

_HREF = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


def cosine(left: np.ndarray, right: np.ndarray) -> float:
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denom <= 1e-8:
        return 0.0
    return float(np.dot(left, right) / denom)


def ndcg_at_k(relevances: list[float], k: int = 10) -> float:
    chosen = relevances[:k]
    if not chosen:
        return 0.0

    def dcg(values: list[float]) -> float:
        return sum(value / math.log2(index + 2) for index, value in enumerate(values))

    ideal = sorted(relevances, reverse=True)[:k]
    ideal_dcg = dcg(ideal)
    if ideal_dcg <= 0:
        return 0.0
    return dcg(chosen) / ideal_dcg


def diversify(
    items: list,
    *,
    scores: list[float],
    vectors: list[np.ndarray | None],
    clusters: list[str | None],
    lam: float = 0.7,
    cluster_cap: float = 0.3,
    novelty_share: float = 0.15,
    near_dup: float = 0.92,
) -> list:
    """MMR plus a cluster cap and a novelty share. Items without vectors pass through."""
    if not items:
        return []
    order = sorted(range(len(items)), key=lambda index: scores[index], reverse=True)
    cap = max(1, math.floor(len(items) * cluster_cap))
    novelty_target = max(0, round(len(items) * novelty_share))
    chosen: list[int] = []
    used: Counter[str] = Counter()
    novelty_used = 0

    def too_close(index: int) -> bool:
        vector = vectors[index]
        if vector is None:
            return False
        for picked in chosen:
            other = vectors[picked]
            if other is not None and cosine(vector, other) >= near_dup:
                return True
        return False

    while order and len(chosen) < len(items):
        best_index = None
        best_value = -1e9
        for index in order:
            cluster = clusters[index] or ""
            if cluster and used[cluster] >= cap:
                continue
            if too_close(index):
                continue
            redundancy = 0.0
            vector = vectors[index]
            if vector is not None and chosen:
                present = [
                    other for other in (vectors[picked] for picked in chosen) if other is not None
                ]
                if present:
                    redundancy = max(cosine(vector, other) for other in present)
            value = lam * scores[index] - (1 - lam) * max(redundancy, 0.0)
            if best_index is None or value > best_value:
                best_value = value
                best_index = index
        if best_index is None:
            break
        chosen.append(best_index)
        order.remove(best_index)
        cluster = clusters[best_index] or ""
        if cluster:
            used[cluster] += 1

    # Fill missing novelty by replacing distinct non-novelty slots from the end.
    novelty_used = sum(1 for index in chosen if scores[index] < 0.45)
    if novelty_used < novelty_target:
        tail = [
            index for index in range(len(items)) if index not in chosen and scores[index] < 0.45
        ]
        slots = [pos for pos in range(len(chosen) - 1, -1, -1) if scores[chosen[pos]] >= 0.45]
        for index in tail:
            if novelty_used >= novelty_target or not slots:
                break
            cluster = clusters[index] or ""
            if cluster and used[cluster] >= cap:
                continue
            if too_close(index):
                continue
            pos = slots.pop(0)
            previous = chosen[pos]
            previous_cluster = clusters[previous] or ""
            if previous_cluster:
                used[previous_cluster] -= 1
            chosen[pos] = index
            if cluster:
                used[cluster] += 1
            novelty_used += 1
    return [items[index] for index in chosen]


def outbound_links(text: str, *, source_host: str = "") -> list[str]:
    found: list[str] = []
    host = source_host.lower().removeprefix("www.")
    for match in _HREF.findall(text or ""):
        url = match.rstrip(").,]")
        link_host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        if host and link_host == host:
            continue
        if url not in found:
            found.append(url)
    return found
