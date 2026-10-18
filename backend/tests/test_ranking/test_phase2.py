"""Phase 2 ranking: features, interests, learning, retrieval, and the eval gate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.services.embeddings.registry import (
    MINILM,
    NOMIC,
    active_spec,
    encode_with_spec,
    hash_embed,
    same_model,
    spec_for,
)
from app.services.embeddings.retrieval import backfill_batch, compare
from app.services.embeddings.text import embedding_pieces, pool_vectors, prefix_only
from app.services.ranking.contract import (
    beta_trust,
    label_event,
    preferred_hour,
    temporal_score,
)
from app.services.ranking.interests import (
    diversify,
    ndcg_at_k,
)
from app.services.ranking.learning import (
    MIN_PAIRS,
    RANKER_VERSION,
    EvalReport,
    WeightState,
    debiased_recovers_better,
    explain,
    exploration_plan,
    faithful,
    prior_weights,
    project_simplex,
    score_matrix,
    synthetic_eval,
    update_weights,
)


def _axis(index: int) -> np.ndarray:
    vector = np.zeros(8, dtype=float)
    vector[index] = 1.0
    return vector


def test_labels_ignore_unviewed_skips_and_keep_viewed_ones():
    assert label_event(skipped=True, viewed=False) is None
    assert label_event(skipped=True, viewed=True) == (0.0, 0.5)
    assert label_event(rating=1) == (1.0, 1.0)
    assert label_event(completion=0.1)[0] < label_event(completion=0.9)[0]
    assert label_event(saved=True)[0] >= 0.9


@pytest.mark.asyncio
async def test_suggestion_signal_fires_for_discovery_origin():
    """A discovery item scores above neutral even with no embedding or history."""
    import uuid as _uuid

    from app.models.content import ContentItem
    from app.services.ranking.contract import SIGNALS
    from app.services.ranking.ranker import UserRankingState, score_candidates

    content = ContentItem(
        id=_uuid.uuid4(), url="https://d.example/x", title="x", origin="discovery"
    )
    state = UserRankingState(
        user_id=_uuid.uuid4(),
        weights={name: 1 / len(SIGNALS) for name in SIGNALS},
        history=[],
        interests=[],
        bridges=[],
        feeds={},
        source_feed_key={},
        prefers_fresh=True,
        novelty_target=0.35,
    )
    scored = score_candidates(state, [content])[0]
    assert scored.features["suggestion"] > 0.5
    assert "suggestion" not in scored.no_data


def test_diversity_cap_and_near_duplicates():
    items = list(range(6))
    scores = [0.9, 0.8, 0.7, 0.2, 0.15, 0.1]
    same = np.ones(8)
    vectors = [same, same, _axis(0), _axis(1), _axis(2), _axis(3)]
    clusters = ["a", "a", "a", "a", "b", "c"]
    picked = diversify(
        items,
        scores=scores,
        vectors=vectors,
        clusters=clusters,
        cluster_cap=0.3,
        novelty_share=0.15,
        near_dup=0.99,
    )
    assert picked.count(0) + picked.count(1) <= 1
    assert sum(1 for item in picked if clusters[item] == "a") <= max(1, int(len(items) * 0.3))
    novel = [item for item in picked if scores[item] < 0.45]
    assert abs(len(novel) - round(len(items) * 0.15)) <= 1 or len(picked) < len(items)


def test_temporal_saturation_and_trust_prior():
    now = datetime(2026, 9, 25, tzinfo=UTC)
    first = temporal_score(
        published_at=now - timedelta(hours=2),
        now=now,
        same_event_count=1,
        user_prefers_fresh=True,
    )
    sixth = temporal_score(
        published_at=now - timedelta(hours=2),
        now=now,
        same_event_count=6,
        user_prefers_fresh=True,
    )
    assert sixth < first
    cold = beta_trust(0, 0)
    assert 0.4 < cold.mean < 0.6
    assert cold.low <= cold.mean <= cold.high
    aged = beta_trust(20, 0, age_days=0)
    decayed = beta_trust(20, 0, age_days=180)
    assert decayed.mean < aged.mean
    assert preferred_hour([7, 7, 21]) == 7


def test_learning_waits_for_evidence_then_moves_and_stays_finite():
    prior = prior_weights()
    state = WeightState(prior, RANKER_VERSION, 0, 0)
    positive = np.array([1.0, 0, 0, 0, 0, 0, 0, 0])
    negative = np.zeros(8)
    for _ in range(MIN_PAIRS - 1):
        state = update_weights(state, positive, negative)
    assert np.allclose(state.weights, project_simplex(prior))
    for _ in range(40):
        state = update_weights(state, positive, negative, lr=0.2, l2=0.01)
    assert np.isfinite(state.weights).all()
    assert abs(float(state.weights.sum()) - 1) < 1e-6
    assert state.weights[0] >= state.weights[1]
    text, contributions = explain(
        {"semantic": 0.5, "novelty": 0.5}, {"semantic": 0.5, "novelty": 0.5}
    )
    assert faithful(contributions, 0.5)
    assert "semantic" in text or "novelty" in text


def test_exploration_ipw_and_eval_gate():
    import random

    plan = exploration_plan([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2], rng=random.Random(1))
    assert plan
    assert all(row["ipw"] <= 5 for row in plan)
    assert debiased_recovers_better()
    report = synthetic_eval()
    assert report.beats_baselines()
    assert report.oracle_ndcg >= report.prs_ndcg
    assert report.prs_ndcg > report.no_learning_ndcg
    assert report.margin_over_no_learning >= 0.05
    assert report.prs_ndcg > report.chronological_ndcg
    assert report.prs_ndcg > report.semantic_ndcg
    assert report.prs_ndcg > report.random_ndcg
    # Gate requires beating the no-learning baseline:
    failing_report = EvalReport(
        prs_ndcg=report.no_learning_ndcg + 0.01,
        chronological_ndcg=0.5,
        semantic_ndcg=0.5,
        random_ndcg=0.5,
        no_learning_ndcg=report.no_learning_ndcg,
        oracle_ndcg=1.0,
        margin=0.2,
        margin_over_no_learning=0.01,
    )
    assert not failing_report.beats_baselines()
    matrix = score_matrix(np.full(8, 0.125), np.ones((1000, 8)))
    assert matrix.shape == (1000, 1)


def test_embedding_registry_retrieval_and_windows():
    assert active_spec(model=NOMIC, cutover=False).name == MINILM
    assert active_spec(model=NOMIC, cutover=True).name == MINILM
    assert spec_for(NOMIC).dim == 768
    assert spec_for(NOMIC).prefix_document.startswith("search_document")
    encoded = encode_with_spec("search_document topic", spec_for(NOMIC), query=False)
    assert len(encoded) == 768
    assert same_model(MINILM, 384, spec_for(MINILM))
    assert not same_model(NOMIC, 768, spec_for(MINILM))
    body = (
        " ".join(f"early{i}" for i in range(500))
        + " latetopic "
        + " ".join(f"tail{i}" for i in range(20))
    )
    pieces = embedding_pieces(title="Note", lead="Lead", body=body)
    assert any("latetopic" in piece for piece in pieces)
    assert "latetopic" not in prefix_only(title="Note", body=body)
    prefix_body = " ".join(body.split()[:180])
    full = pool_vectors([hash_embed(piece, 16) for piece in pieces])
    prefix = pool_vectors(
        [
            hash_embed(piece, 16)
            for piece in embedding_pieces(title="Note", lead="Lead", body=prefix_body)
        ]
    )
    assert full != prefix
    report = compare()
    assert report["pairs"] == 200
    assert report["full_wins"]
    rows = [{"id": index} for index in range(1000)]
    first = backfill_batch(rows, model=MINILM, dim=384, version="1", cursor=0, size=400)
    second = backfill_batch(
        rows, model=MINILM, dim=384, version="1", cursor=first["next_cursor"], size=600
    )
    assert second["done"]
    assert rows[0]["embedding_model"] == MINILM
    assert rows[-1]["embedding_dim"] == 384


@pytest.mark.asyncio
async def test_stamp_stored_embeddings_commits(db_session):
    from app.models.content import ContentItem
    from app.services.embeddings.retrieval import stamp_stored_embeddings

    item = ContentItem(url="https://1.1.1.1/a", title="A", embedding=[0.0] * 384)
    db_session.add(item)
    await db_session.commit()
    result = await stamp_stored_embeddings(
        db_session, cursor=None, size=10, model=MINILM, dim=384, version="1"
    )
    assert result["stamped"] == 1
    assert result["done"]
    await db_session.refresh(item)
    assert item.embedding_model == MINILM
    assert item.embedding_dim == 384
