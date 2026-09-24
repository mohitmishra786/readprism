"""Phase 2 ranking: features, interests, learning, retrieval, and the eval gate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

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
from app.services.ranking.phase2.contract import (
    beta_trust,
    content_quality_score,
    features_from_scores,
    history_without_target,
    label_event,
    predicted_reading_depth,
    preferred_hour,
    temporal_score,
)
from app.services.ranking.phase2.interests import (
    cluster_medoids,
    discovery_candidates,
    diversify,
    mean_vector_score,
    ndcg_at_k,
    semantic_score,
)
from app.services.ranking.phase2.learning import (
    MIN_PAIRS,
    RANKER_VERSION,
    WeightState,
    debiased_recovers_better,
    explain,
    exploration_plan,
    faithful,
    prior_weights,
    project_simplex,
    score_matrix,
    synthetic_eval,
    task_dedup_key,
    update_weights,
)


def _axis(index: int) -> np.ndarray:
    vector = np.zeros(8, dtype=float)
    vector[index] = 1.0
    return vector


def test_features_stay_in_unit_interval_and_drop_the_target_row():
    features = features_from_scores({"semantic": 2.0, "novelty": -1, "reading_depth": float("nan")})
    assert all(0.0 <= value <= 1.0 for value in features.as_dict().values())
    target = SimpleNamespace(
        content_item_id="self", read_completion_pct=1.0, source_id="s", length_bucket="short"
    )
    other = SimpleNamespace(
        content_item_id="other", read_completion_pct=0.2, source_id="s", length_bucket="short"
    )
    assert history_without_target([target, other], "self") == [other]
    depth = predicted_reading_depth(
        [target, other], item_id="self", source_id="s", length_bucket="short"
    )
    assert depth < 0.5


def test_labels_ignore_unviewed_skips_and_keep_viewed_ones():
    assert label_event(skipped=True, viewed=False) is None
    assert label_event(skipped=True, viewed=True) == (0.0, 0.5)
    assert label_event(rating=1) == (1.0, 1.0)
    assert label_event(completion=0.1)[0] < label_event(completion=0.9)[0]
    assert label_event(saved=True)[0] >= 0.9


def test_two_topic_user_prefers_medoids_over_the_mean():
    rust = [_axis(0) for _ in range(6)]
    city = [_axis(1) for _ in range(6)]
    vectors = rust + city
    clusters = cluster_medoids(vectors, labels=["rust"] * 6 + ["cities"] * 6)
    assert len(clusters) == 2
    blend = (_axis(0) + _axis(1)) / np.sqrt(2)
    candidates = [_axis(0), _axis(1), blend]
    relevance = [1.0, 1.0, 0.0]
    medoid_order = sorted(
        range(3),
        key=lambda index: semantic_score(candidates[index], vectors, clusters),
        reverse=True,
    )
    mean_order = sorted(
        range(3),
        key=lambda index: mean_vector_score(candidates[index], vectors),
        reverse=True,
    )
    assert ndcg_at_k([relevance[index] for index in medoid_order]) > ndcg_at_k(
        [relevance[index] for index in mean_order]
    )


def test_discovery_pool_and_suggestion_origin():
    rows = discovery_candidates(
        followed_texts=[("See https://1.1.1.1/story", "example.com")], topics=["rust"]
    )
    assert rows[0]["origin"] == "discovery"
    assert any(row["topic"] == "rust" for row in rows)
    assert discovery_candidates(followed_texts=[], topics=None)


@pytest.mark.asyncio
async def test_suggestion_signal_fires_for_discovery_origin():
    from app.services.ranking.signals import UserInterestGraph, suggestion

    content = SimpleNamespace(origin="discovery", embedding=None, id="x")
    user = SimpleNamespace(created_at=datetime.now(UTC))
    score = await suggestion.compute(content, user, [], UserInterestGraph(nodes=[], edges=[]), None)
    assert score == 0.8


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
    assert (
        content_quality_score(word_count=1200, link_count=4, citation_count=2, has_code=True) > 0.5
    )


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
    matrix = score_matrix(np.full(8, 0.125), np.ones((1000, 8)))
    assert matrix.shape == (1000, 1)
    assert task_dedup_key("embed", "abc") == "embed:abc"


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
