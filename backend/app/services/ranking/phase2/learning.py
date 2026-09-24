"""Weight learning, exploration, explanations, and the synthetic eval."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np

from app.services.ranking.phase2.contract import SIGNALS, clamp01
from app.services.ranking.phase2.interests import ndcg_at_k

RANKER_VERSION = "2"


def task_dedup_key(task: str, *parts: object) -> str:
    return task + ":" + ":".join(str(part) for part in parts)


FLOOR = 0.02
MIN_PAIRS = 30


def prior_weights() -> np.ndarray:
    weights = np.full(len(SIGNALS), 1.0 / len(SIGNALS))
    return project_simplex(weights)


def project_simplex(weights: np.ndarray, floor: float = FLOOR) -> np.ndarray:
    count = len(weights)
    floor = min(floor, 1.0 / count)
    cleaned = np.array(
        [0.0 if not math.isfinite(float(value)) else max(0.0, float(value)) for value in weights]
    )
    cleaned = cleaned + floor
    total = float(cleaned.sum()) or 1.0
    projected = cleaned / total
    # A second pass keeps the floor after normalization when it is feasible.
    if float(projected.min()) + 1e-9 < floor:
        projected = np.maximum(projected, floor)
        projected = projected / float(projected.sum())
    return projected


def sigmoid(value: float) -> float:
    if value > 30:
        return 1.0
    if value < -30:
        return 0.0
    return 1.0 / (1.0 + math.exp(-value))


@dataclass
class WeightState:
    weights: np.ndarray
    version: str
    updates: int
    pairs_seen: int

    def as_dict(self) -> dict[str, float]:
        return {name: float(self.weights[index]) for index, name in enumerate(SIGNALS)}


def update_weights(
    state: WeightState,
    positive: np.ndarray,
    negative: np.ndarray,
    *,
    lr: float = 0.05,
    l2: float = 0.1,
    prior: np.ndarray | None = None,
) -> WeightState:
    """One pairwise logistic step. Below MIN_PAIRS the weights stay at the prior."""
    prior = prior_weights() if prior is None else prior
    seen = state.pairs_seen + 1
    if seen < MIN_PAIRS:
        return WeightState(project_simplex(prior), state.version, state.updates, seen)
    difference = positive - negative
    prediction = sigmoid(float(np.dot(state.weights, difference)))
    gradient = (prediction - 1.0) * difference + l2 * (state.weights - prior)
    step = lr / math.sqrt(state.updates + 1)
    updated = project_simplex(state.weights - step * gradient)
    return WeightState(updated, state.version, state.updates + 1, seen)


def exploration_count(item_count: int) -> int:
    return min(2, max(0, math.ceil(0.10 * item_count)))


def exploration_plan(
    scores: list[float],
    *,
    rng: random.Random,
    temperature: float = 0.5,
) -> list[dict]:
    """Pick ε slots from ranks 6–40. Each row records its propensity."""
    count = exploration_count(len(scores))
    if count == 0 or len(scores) < 6:
        return []
    pool = list(range(5, min(40, len(scores))))
    if not pool:
        return []
    pool_scores = np.array([scores[index] for index in pool], dtype=float)
    scaled = pool_scores / max(temperature, 1e-6)
    scaled = scaled - float(scaled.max())
    weights = np.exp(scaled)
    weights = weights / float(weights.sum())
    chosen: list[dict] = []
    available = list(range(len(pool)))
    for _ in range(min(count, len(available))):
        mass = float(sum(weights[option] for option in available)) or 1.0
        draw = rng.random() * mass
        cursor = 0.0
        pick = available[-1]
        for option in available:
            cursor += float(weights[option])
            if draw <= cursor:
                pick = option
                break
        propensity = float(weights[pick]) / mass
        chosen.append(
            {
                "rank": pool[pick] + 1,
                "index": pool[pick],
                "propensity": propensity,
                "exploration": True,
                "ipw": clipped_ipw(propensity),
            }
        )
        available.remove(pick)
    return chosen


def clipped_ipw(propensity: float, cap: float = 5.0) -> float:
    if propensity <= 0:
        return cap
    return min(cap, 1.0 / propensity)


def explain(scores: dict[str, float], weights: dict[str, float]) -> tuple[str, dict[str, float]]:
    contributions = {
        name: float(weights.get(name, 0.0)) * float(scores.get(name, 0.0)) for name in SIGNALS
    }
    ordered = sorted(contributions, key=lambda name: contributions[name], reverse=True)
    lead = ordered[0] if ordered else "semantic"
    text = f"Ranked mainly by {lead.replace('_', ' ')}"
    return text, contributions


def faithful(contributions: dict[str, float], score: float, tol: float = 1e-6) -> bool:
    return abs(sum(contributions.values()) - score) <= tol


def dot_score(weights: np.ndarray, features: np.ndarray) -> float:
    return clamp01(float(np.dot(weights, features)))


def score_matrix(weights: np.ndarray, features: np.ndarray) -> np.ndarray:
    return np.clip(features @ weights.reshape(-1, 1), 0.0, 1.0)


@dataclass
class EvalReport:
    prs_ndcg: float
    chronological_ndcg: float
    semantic_ndcg: float
    random_ndcg: float
    margin: float

    def beats_baselines(self, margin: float = 0.05) -> bool:
        return (
            self.prs_ndcg >= self.chronological_ndcg + margin
            and self.prs_ndcg >= self.semantic_ndcg + margin
            and self.prs_ndcg >= self.random_ndcg + margin
        )


def synthetic_eval(*, users: int = 12, items: int = 40, seed: int = 7) -> EvalReport:
    """Learn weights on a training split, then score a held-out split.

    Relevance is the persona's dominant feature. PRS is `score_matrix` after
    `update_weights`. It is not an oracle sort of the labels.
    """
    rng = np.random.default_rng(seed)
    py_rng = random.Random(seed)
    prs_scores: list[float] = []
    chrono_scores: list[float] = []
    semantic_scores: list[float] = []
    random_scores: list[float] = []
    split = items // 2
    for persona in range(users):
        dominant = persona % len(SIGNALS)
        features = rng.random((items, len(SIGNALS)))
        relevance = features[:, dominant]
        train = features[:split]
        train_rel = relevance[:split]
        hold = features[split:]
        hold_rel = relevance[split:]
        state = WeightState(prior_weights(), RANKER_VERSION, 0, 0)
        for _ in range(90):
            left = py_rng.randrange(split)
            right = py_rng.randrange(split)
            if train_rel[left] == train_rel[right]:
                continue
            if train_rel[left] > train_rel[right]:
                positive, negative = train[left], train[right]
            else:
                positive, negative = train[right], train[left]
            state = update_weights(state, positive, negative, lr=0.4, l2=0.01)
        scored = score_matrix(state.weights, hold).reshape(-1)
        prs_order = list(np.argsort(-scored))
        chrono_order = list(range(split))
        semantic_order = list(np.argsort(-hold[:, 0]))
        random_order = list(rng.permutation(split))
        prs_scores.append(ndcg_at_k([float(hold_rel[index]) for index in prs_order]))
        chrono_scores.append(ndcg_at_k([float(hold_rel[index]) for index in chrono_order]))
        semantic_scores.append(ndcg_at_k([float(hold_rel[index]) for index in semantic_order]))
        random_scores.append(ndcg_at_k([float(hold_rel[index]) for index in random_order]))
    prs = float(np.mean(prs_scores))
    chrono = float(np.mean(chrono_scores))
    semantic = float(np.mean(semantic_scores))
    random_ndcg = float(np.mean(random_scores))
    return EvalReport(prs, chrono, semantic, random_ndcg, prs - chrono)


def debiased_recovers_better(*, seed: int = 3) -> bool:
    """A confounder decides position. IPW should track true relevance more closely."""
    rng = random.Random(seed)
    true = np.zeros(8)
    true[0] = 1.0
    naive = np.zeros(8)
    debiased = np.zeros(8)
    naive_n = 0.0
    debiased_n = 0.0
    for _ in range(400):
        features = np.array([rng.random() for _ in range(8)])
        relevance = float(features[0])
        position = min(9, int((1.0 - features[1]) * 9))
        examination = 1.0 / (position + 1)
        if rng.random() >= relevance * examination:
            continue
        naive += features
        naive_n += 1
        weight = clipped_ipw(examination)
        debiased += features * weight
        debiased_n += weight
    if naive_n == 0 or debiased_n == 0:
        return False
    naive = naive / naive_n
    debiased = debiased / debiased_n
    return float(debiased[0] - debiased[1]) >= float(naive[0] - naive[1])
