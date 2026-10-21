"""Standalone unit tests for weirling-rank package (#245)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from weirling_rank.contract import (
    SIGNALS,
    beta_trust,
    clamp01,
    length_bucket,
)
from weirling_rank.ranker import (
    average_linkage,
    build_interests,
    rank_candidates,
)
from weirling_rank.types import (
    Candidate,
    HistoryRow,
    Interest,
    UserRankingState,
)

UTC = timezone.utc
DIM = 64
NOW = datetime(2026, 10, 21, 12, tzinfo=UTC)


def unit(*axes: float) -> np.ndarray:
    v = np.zeros(DIM, dtype=np.float32)
    for i, val in enumerate(axes):
        v[i] = val
    norm = float(np.linalg.norm(v))
    return v / norm if norm > 1e-8 else v


def test_clamp01():
    assert clamp01(-5.0) == 0.0
    assert clamp01(5.0) == 1.0
    assert clamp01(0.7) == 0.7
    assert clamp01(float("nan")) == 0.5
    assert clamp01(float("inf")) == 0.5


def test_length_bucket():
    assert length_bucket(100) == "short"
    assert length_bucket(500) == "medium"
    assert length_bucket(2500) == "long"
    assert length_bucket(None) == "short"


def test_beta_trust():
    trust = beta_trust(successes=10, failures=0)
    assert 0.7 < trust.mean <= 1.0
    assert trust.low < trust.mean < trust.high

    decayed = beta_trust(successes=10, failures=0, age_days=180, half_life_days=90)
    assert decayed.mean < trust.mean


def test_average_linkage_clustering():
    v1 = unit(1.0, 0.0)
    v2 = unit(0.99, 0.01)
    v3 = unit(0.0, 1.0)
    matrix = np.stack([v1, v2, v3])
    groups = average_linkage(matrix, threshold=0.1)
    # v1 and v2 should cluster together, v3 separate
    assert len(groups) == 2
    lens = sorted(len(g) for g in groups)
    assert lens == [1, 2]


def test_build_interests_medoid_selection():
    v1 = unit(1.0, 0.0)
    v2 = unit(0.99, 0.05)
    candidates = [(v1, 1.0, "topic-a"), (v2, 0.5, "topic-a-alt")]
    interests = build_interests(candidates)
    assert len(interests) == 1
    assert interests[0].importance == 1.5


def test_score_and_rank_candidates():
    v_ai = unit(1.0, 0.0)
    v_cook = unit(0.0, 1.0)

    cand_ai = Candidate(
        id="cand-1",
        title="AI Engineering Systems",
        embedding=v_ai,
        word_count=1200,
        published_at=NOW - timedelta(hours=2),
    )
    cand_cook = Candidate(
        id="cand-2",
        title="Rustic Bread Baking",
        embedding=v_cook,
        word_count=800,
        published_at=NOW - timedelta(hours=5),
    )

    state = UserRankingState(
        user_id="user-1",
        weights={s: 1.0 / len(SIGNALS) for s in SIGNALS},
        history=[
            HistoryRow(
                content_id="hist-1",
                vector=v_ai,
                words=1000,
                completion=0.9,
                rating=1,
                opened_at=NOW - timedelta(days=1),
                created_at=NOW - timedelta(days=1),
                title="Previous AI read",
            )
        ],
        interests=[Interest(vector=v_ai, importance=1.0, label="AI Engineering")],
        prefers_fresh=True,
        now=NOW,
    )

    scored = rank_candidates(state, [cand_ai, cand_cook])
    assert len(scored) == 2
    # cand_ai matches history, positive rating, and interest; should rank first
    assert scored[0].item.id == "cand-1"
    assert scored[0].prs > scored[1].prs
    assert scored[0].features["semantic"] > scored[1].features["semantic"]
    assert "semantic" not in scored[0].no_data
    assert scored[0].explanation is not None
