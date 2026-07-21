from __future__ import annotations

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.services.ranking.signals import UserInterestGraph
from app.utils.cache import cache_get, cache_set
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


# Edges at or above this weight join two topics into one interest cluster.
CLUSTER_EDGE_THRESHOLD = 0.3
# Edges at or above this (stronger) weight also contribute a "bridge" vector at
# the midpoint of the two topics, giving transitive relevance (audit 05-4).
BRIDGE_EDGE_THRESHOLD = 0.5


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def _bridge_vectors(graph: UserInterestGraph) -> list[np.ndarray]:
    """Vectors at the midpoint of strongly-connected topic pairs.

    Implements the spec's transitive relevance: content at the *intersection* of
    two strongly-connected interests (e.g. compiler-optimization ∩ language-design)
    scores highly via the bridge even if it's not near either topic alone —
    something a per-node or per-cluster centroid can't capture (audit 05-4).
    """
    by_id = {n.id: n for n in graph.nodes if n.topic_embedding is not None}
    vectors: list[np.ndarray] = []
    for edge in graph.edges:
        if edge.edge_weight < BRIDGE_EDGE_THRESHOLD:
            continue
        a, b = by_id.get(edge.from_node_id), by_id.get(edge.to_node_id)
        if a is None or b is None:
            continue
        mid = (
            np.array(a.topic_embedding, dtype=np.float32)
            + np.array(b.topic_embedding, dtype=np.float32)
        ) / 2.0
        norm = np.linalg.norm(mid)
        if norm > 0:
            vectors.append(mid / norm)
    return vectors


def _cluster_vectors(graph: UserInterestGraph) -> list[np.ndarray]:
    """Group interest nodes into clusters (graph-connected topics) and return one
    weighted, normalized vector per cluster.

    Averaging *all* node embeddings into a single vector collapses a multi-interest
    user (e.g. cooking + compilers) to a centroid near neither — the classic
    averaged-embedding failure. Clustering by the interest graph's co-occurrence
    edges preserves each distinct interest so scoring can match any of them
    (audit 05-2).
    """
    nodes = [n for n in graph.nodes if n.topic_embedding is not None]
    if not nodes:
        return []

    # Union-find over strong edges to form connected-topic clusters.
    index = {n.id: i for i, n in enumerate(nodes)}
    parent = list(range(len(nodes)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        parent[find(a)] = find(b)

    for edge in graph.edges:
        if edge.edge_weight >= CLUSTER_EDGE_THRESHOLD:
            ia, ib = index.get(edge.from_node_id), index.get(edge.to_node_id)
            if ia is not None and ib is not None:
                union(ia, ib)

    clusters: dict[int, list] = {}
    for i, node in enumerate(nodes):
        clusters.setdefault(find(i), []).append(node)

    vectors: list[np.ndarray] = []
    for cluster_nodes in clusters.values():
        weights = np.array([n.weight for n in cluster_nodes], dtype=np.float32)
        embeddings = np.array([n.topic_embedding for n in cluster_nodes], dtype=np.float32)
        weighted = (embeddings * weights[:, np.newaxis]).sum(axis=0)
        norm = np.linalg.norm(weighted)
        if norm > 0:
            vectors.append(weighted / norm)
    return vectors


async def compute(
    content: ContentItem,
    user: User,
    interaction_history: list[UserContentInteraction],
    interest_graph: UserInterestGraph,
    session: AsyncSession,
) -> float:
    match_vecs = _cluster_vectors(interest_graph) + _bridge_vectors(interest_graph)
    if not match_vecs:
        return 0.5

    content_vec = await _get_content_embedding(content)
    if content_vec is None:
        # Enqueue embedding computation and return neutral
        from app.workers.tasks.compute_embeddings import compute_embedding_for_item

        compute_embedding_for_item.delay(str(content.id))
        return 0.5

    # Max similarity across per-cluster vectors AND transitive bridge vectors:
    # content near ANY distinct interest — or the intersection of two connected
    # interests — scores highly, instead of being averaged down.
    best_sim = max(_cosine(vec, content_vec) for vec in match_vecs)
    return (best_sim + 1.0) / 2.0


async def _get_user_interest_vector(user: User, graph: UserInterestGraph) -> np.ndarray | None:
    """Single averaged interest vector — retained for callers that need one broad
    centroid (collaborative warmup, cache warmers). The semantic *signal* now uses
    per-cluster max similarity via `_cluster_vectors` instead."""
    cache_key = f"interest_vec:{user.id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return np.array(cached, dtype=np.float32)

    nodes_with_embeddings = [n for n in graph.nodes if n.topic_embedding is not None]
    if not nodes_with_embeddings:
        return None

    weights = np.array([n.weight for n in nodes_with_embeddings], dtype=np.float32)
    embeddings = np.array([n.topic_embedding for n in nodes_with_embeddings], dtype=np.float32)
    weighted = (embeddings * weights[:, np.newaxis]).sum(axis=0)
    norm = np.linalg.norm(weighted)
    if norm > 0:
        weighted = weighted / norm

    await cache_set(cache_key, weighted.tolist(), ttl_seconds=3600)
    return weighted


async def _get_content_embedding(content: ContentItem) -> np.ndarray | None:
    if content.embedding is None:
        return None
    return np.array(content.embedding, dtype=np.float32)
