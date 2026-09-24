"""Multi-interest medoids, diversity re-rank, and the discovery pool.

Clustering is average-linkage agglomerative with a cosine-distance threshold,
which is the small-n form of the medoid profile. Labels are supplied by the
caller so this module does not call an LLM.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from urllib.parse import urlparse

import numpy as np

_HREF = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)

SEED_FEEDS = (
    {"topic": "systems", "title": "Hacker News", "url": "https://hnrss.org/frontpage"},
    {"topic": "systems", "title": "Lobsters", "url": "https://lobste.rs/rss"},
    {"topic": "research", "title": "arXiv cs.LG", "url": "https://rss.arxiv.org/rss/cs.LG"},
    {"topic": "rust", "title": "Rust Blog", "url": "https://blog.rust-lang.org/feed.xml"},
    {
        "topic": "security",
        "title": "Google Project Zero",
        "url": "https://googleprojectzero.blogspot.com/feeds/posts/default",
    },
)


@dataclass
class InterestCluster:
    member_indexes: list[int]
    medoid_index: int
    importance: float
    label: str


def cosine(left: np.ndarray, right: np.ndarray) -> float:
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denom <= 1e-8:
        return 0.0
    return float(np.dot(left, right) / denom)


def _distance(left: np.ndarray, right: np.ndarray) -> float:
    return 1.0 - cosine(left, right)


def cluster_medoids(
    vectors: list[np.ndarray],
    *,
    distance_threshold: float = 0.45,
    importances: list[float] | None = None,
    labels: list[str] | None = None,
) -> list[InterestCluster]:
    count = len(vectors)
    if count == 0:
        return []
    groups: list[list[int]] = [[index] for index in range(count)]

    def average_distance(left: list[int], right: list[int]) -> float:
        total = 0.0
        for i in left:
            for j in right:
                total += _distance(vectors[i], vectors[j])
        return total / (len(left) * len(right))

    while len(groups) > 1:
        best: tuple[int, int] | None = None
        best_distance = distance_threshold + 1
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                distance = average_distance(groups[i], groups[j])
                if distance < best_distance:
                    best_distance = distance
                    best = (i, j)
        if best is None or best_distance > distance_threshold:
            break
        i, j = best
        merged = groups[i] + groups[j]
        groups = [group for index, group in enumerate(groups) if index not in {i, j}]
        groups.append(merged)

    weights = importances or [1.0] * count
    names = labels or [""] * count
    clusters: list[InterestCluster] = []
    for group in groups:
        centroid = np.mean([vectors[index] for index in group], axis=0)
        medoid = min(group, key=lambda index: _distance(vectors[index], centroid))
        importance = sum(weights[index] for index in group)
        label_counts = Counter(names[index] for index in group if names[index])
        label = label_counts.most_common(1)[0][0] if label_counts else "interest"
        clusters.append(
            InterestCluster(
                member_indexes=group,
                medoid_index=medoid,
                importance=importance,
                label=label,
            )
        )
    clusters.sort(key=lambda cluster: cluster.importance, reverse=True)
    return clusters


def semantic_score(
    vector: np.ndarray, vectors: list[np.ndarray], clusters: list[InterestCluster]
) -> float:
    if not clusters:
        return 0.5
    ranked = clusters[:3]
    peak = max(cluster.importance for cluster in ranked) or 1.0
    best = 0.0
    for cluster in ranked:
        weight = cluster.importance / peak
        best = max(best, weight * max(cosine(vector, vectors[cluster.medoid_index]), 0.0))
    return max(0.0, min(1.0, best))


def mean_vector_score(vector: np.ndarray, vectors: list[np.ndarray]) -> float:
    if not vectors:
        return 0.5
    mean = np.mean(vectors, axis=0)
    return max(0.0, min(1.0, (cosine(vector, mean) + 1) / 2))


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


def discovery_candidates(
    *,
    followed_texts: list[tuple[str, str]],
    topics: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, str]]:
    """Candidates the user does not already follow. No network."""
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    wanted = {topic.lower() for topic in topics} if topics else set()
    for topic_text, source_host in followed_texts:
        for url in outbound_links(topic_text, source_host=source_host):
            if url in seen:
                continue
            seen.add(url)
            rows.append({"url": url, "title": url, "origin": "discovery", "topic": "outbound"})
            if len(rows) >= limit:
                return rows
    for seed in SEED_FEEDS:
        if wanted and seed["topic"] not in wanted:
            continue
        if seed["url"] in seen:
            continue
        rows.append(
            {
                "url": seed["url"],
                "title": seed["title"],
                "origin": "discovery",
                "topic": seed["topic"],
            }
        )
        if len(rows) >= limit:
            break
    return rows
