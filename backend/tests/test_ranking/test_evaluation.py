"""Ranking-eval math + endpoint (audit 05-1 / 16-3 / 17-4)."""

from __future__ import annotations

import pytest

from app.services.ranking.evaluation import read_prediction_auc, spearman


def test_auc_perfect_separation():
    # All positives outrank all negatives -> AUC 1.0
    scores = [0.9, 0.8, 0.2, 0.1]
    labels = [True, True, False, False]
    assert read_prediction_auc(scores, labels) == pytest.approx(1.0)


def test_auc_reversed_is_zero():
    scores = [0.1, 0.2, 0.8, 0.9]
    labels = [True, True, False, False]
    assert read_prediction_auc(scores, labels) == pytest.approx(0.0)


def test_auc_chance_is_half():
    # pos={0.9,0.6}, neg={0.8,0.7}: exactly half of pos>neg pairs -> 0.5
    scores = [0.9, 0.8, 0.7, 0.6]
    labels = [True, False, False, True]
    assert read_prediction_auc(scores, labels) == pytest.approx(0.5)


def test_auc_none_when_single_class():
    assert read_prediction_auc([0.5, 0.6], [True, True]) is None
    assert read_prediction_auc([0.5, 0.6], [False, False]) is None


def test_auc_handles_ties():
    scores = [0.5, 0.5, 0.5, 0.5]
    labels = [True, True, False, False]
    assert read_prediction_auc(scores, labels) == pytest.approx(0.5)


def test_spearman_monotonic():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)


def test_spearman_no_variance_is_none():
    assert spearman([1, 1, 1], [1, 2, 3]) is None
    assert spearman([5], [5]) is None


@pytest.mark.asyncio
async def test_ranking_eval_endpoint(client, test_user_data):
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    token = reg.json()["access_token"]
    resp = await client.get(
        "/api/v1/metrics/ranking-eval", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    # No digests yet -> empty eval, nulls rather than errors.
    assert body["n"] == 0
    assert body["read_prediction_auc"] is None
