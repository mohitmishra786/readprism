from __future__ import annotations

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.services.ranking.signals import UserInterestGraph
from app.utils.cache import cache_get, cache_set
from app.utils.embeddings import get_embedding_service
from app.utils.logging import get_logger
from app.config import get_settings

logger = get_logger(__name__)
settings = get_settings()


async def compute(
    content: ContentItem,
    user: User,
    interaction_history: list[UserContentInteraction],
    interest_graph: UserInterestGraph,
    session: AsyncSession,
) -> float:
    # Get user interest vector
    user_vec = await _get_user_interest_vector(user, interest_graph)
    if user_vec is None:
        return 0.5

    # Get content embedding
    content_vec = await _get_content_embedding(content)
    if content_vec is None:
        # Enqueue embedding computation and return neutral
        from app.workers.tasks.compute_embeddings import compute_embedding_for_item
        compute_embedding_for_item.delay(str(content.id))
        return 0.5

    # Cosine similarity mapped to [0, 1]
    sim = float(np.dot(user_vec, content_vec) / (np.linalg.norm(user_vec) * np.linalg.norm(content_vec) + 1e-8))
    return (sim + 1.0) / 2.0


async def _get_user_interest_vector(user: User, graph: UserInterestGraph) -> np.ndarray | None:
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
