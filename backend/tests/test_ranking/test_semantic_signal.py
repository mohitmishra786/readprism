from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.services.ranking.signals import UserInterestGraph
from app.services.ranking.signals.semantic import compute


@pytest.mark.asyncio
async def test_high_similarity_scores_above_threshold():
    """Content semantically close to user interests scores > 0.7."""
    content = MagicMock()
    content.id = uuid.uuid4()
    content.embedding = [0.9, 0.1, 0.0] * 128  # 384-dim vector

    user = MagicMock()
    user.id = uuid.uuid4()

    node = MagicMock()
    node.topic_embedding = [0.9, 0.1, 0.0] * 128  # same direction
    node.weight = 1.0

    graph = UserInterestGraph(nodes=[node], edges=[])
    session = AsyncMock()

    with (
        patch("app.services.ranking.signals.semantic.cache_get", return_value=None),
        patch("app.services.ranking.signals.semantic.cache_set", return_value=True),
    ):
        score = await compute(content, user, [], graph, session)

    assert score > 0.7, f"Expected > 0.7 but got {score}"


@pytest.mark.asyncio
async def test_low_similarity_scores_below_threshold():
    """Content semantically distant from user interests scores < 0.3."""
    content = MagicMock()
    content.id = uuid.uuid4()
    # Orthogonal vector
    content.embedding = [1.0] + [0.0] * 383

    user = MagicMock()
    user.id = uuid.uuid4()

    node = MagicMock()
    node.topic_embedding = [0.0] * 383 + [1.0]  # opposite direction
    node.weight = 1.0

    graph = UserInterestGraph(nodes=[node], edges=[])
    session = AsyncMock()

    with (
        patch("app.services.ranking.signals.semantic.cache_get", return_value=None),
        patch("app.services.ranking.signals.semantic.cache_set", return_value=True),
    ):
        score = await compute(content, user, [], graph, session)

    assert score < 0.6, f"Expected < 0.6 but got {score}"


@pytest.mark.asyncio
async def test_no_embedding_returns_neutral():
    """Content without embedding returns 0.5."""
    content = MagicMock()
    content.id = uuid.uuid4()
    content.embedding = None

    user = MagicMock()
    user.id = uuid.uuid4()
    graph = UserInterestGraph(nodes=[], edges=[])
    session = AsyncMock()

    with patch("app.workers.tasks.compute_embeddings.compute_embedding_for_item") as mock_task:
        mock_task.delay = MagicMock()
        score = await compute(content, user, [], graph, session)

    assert score == 0.5


@pytest.mark.asyncio
async def test_multi_interest_not_averaged_down():
    """A user with two distinct interests scores content near ONE of them highly,
    instead of averaging the two clusters into a centroid near neither (05-2)."""
    content = MagicMock()
    content.id = uuid.uuid4()
    content.embedding = [1.0, 0.0] + [0.0] * 382  # aligned with interest A only

    user = MagicMock()
    user.id = uuid.uuid4()

    node_a = MagicMock()
    node_a.id = uuid.uuid4()
    node_a.topic_embedding = [1.0, 0.0] + [0.0] * 382  # interest A
    node_a.weight = 1.0
    node_b = MagicMock()
    node_b.id = uuid.uuid4()
    node_b.topic_embedding = [0.0, 1.0] + [0.0] * 382  # interest B (orthogonal)
    node_b.weight = 1.0

    # No edge between them -> two separate clusters.
    graph = UserInterestGraph(nodes=[node_a, node_b], edges=[])
    session = AsyncMock()

    score = await compute(content, user, [], graph, session)
    # Averaged vector would give cosine ~0.707 -> ~0.85; max-sim gives ~1.0.
    assert score > 0.95, f"Expected near-1.0 (matched cluster A) but got {score}"


def test_bridge_vectors_only_for_strong_edges():
    """Transitive bridge vectors are created only for strongly-connected pairs (05-4)."""
    from app.services.ranking.signals.semantic import _bridge_vectors

    node_a = MagicMock()
    node_a.id = uuid.uuid4()
    node_a.topic_embedding = [1.0, 0.0] + [0.0] * 382
    node_b = MagicMock()
    node_b.id = uuid.uuid4()
    node_b.topic_embedding = [0.0, 1.0] + [0.0] * 382

    strong = MagicMock()
    strong.from_node_id, strong.to_node_id, strong.edge_weight = node_a.id, node_b.id, 0.6
    weak = MagicMock()
    weak.from_node_id, weak.to_node_id, weak.edge_weight = node_a.id, node_b.id, 0.2

    assert len(_bridge_vectors(UserInterestGraph(nodes=[node_a, node_b], edges=[strong]))) == 1
    assert len(_bridge_vectors(UserInterestGraph(nodes=[node_a, node_b], edges=[weak]))) == 0


@pytest.mark.asyncio
async def test_intersection_content_scores_high_via_bridge():
    """Content at the intersection of two strongly-connected topics scores highly
    even though it's only partially aligned with either topic alone (05-4)."""
    content = MagicMock()
    content.id = uuid.uuid4()
    content.embedding = [0.7071, 0.7071] + [0.0] * 382  # midpoint of A and B

    user = MagicMock()
    user.id = uuid.uuid4()
    node_a = MagicMock()
    node_a.id = uuid.uuid4()
    node_a.topic_embedding = [1.0, 0.0] + [0.0] * 382
    node_a.weight = 1.0
    node_b = MagicMock()
    node_b.id = uuid.uuid4()
    node_b.topic_embedding = [0.0, 1.0] + [0.0] * 382
    node_b.weight = 1.0
    edge = MagicMock()
    edge.from_node_id, edge.to_node_id, edge.edge_weight = node_a.id, node_b.id, 0.7

    graph = UserInterestGraph(nodes=[node_a, node_b], edges=[edge])
    score = await compute(content, user, [], graph, AsyncMock())
    assert score > 0.97, f"Expected intersection content to score ~1.0, got {score}"


def test_explain_top_topics_names_bridge_and_single():
    from app.services.ranking.signals.semantic import explain_top_topics

    node_a = MagicMock()
    node_a.id = uuid.uuid4()
    node_a.topic_label = "Compilers"
    node_a.topic_embedding = [1.0, 0.0] + [0.0] * 382
    node_b = MagicMock()
    node_b.id = uuid.uuid4()
    node_b.topic_label = "Language Design"
    node_b.topic_embedding = [0.0, 1.0] + [0.0] * 382
    edge = MagicMock()
    edge.from_node_id, edge.to_node_id, edge.edge_weight = node_a.id, node_b.id, 0.7
    graph = UserInterestGraph(nodes=[node_a, node_b], edges=[edge])

    # Content at the intersection -> bridge explanation naming both topics.
    bridge_expl = explain_top_topics([0.7071, 0.7071] + [0.0] * 382, graph)
    assert "Compilers" in bridge_expl and "Language Design" in bridge_expl
    assert bridge_expl.startswith("connects your interest in")

    # Content aligned with one topic -> single-topic explanation.
    single_expl = explain_top_topics([1.0, 0.0] + [0.0] * 382, graph)
    assert "Compilers" in single_expl
    assert single_expl.startswith("matches your interest in")

    assert explain_top_topics(None, graph) is None
