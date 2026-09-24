"""Feature contract, labels, content quality, trust, and temporal scales.

Every score is in [0, 1] and can be computed before the user sees the item.
Reading depth is a prediction from other items, never from the candidate's
own interaction row.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

SIGNALS = (
    "semantic",
    "reading_depth",
    "suggestion",
    "explicit_feedback",
    "source_trust",
    "content_quality",
    "temporal_context",
    "novelty",
)


def clamp01(value: float) -> float:
    if math.isnan(value) or math.isinf(value):
        return 0.5
    return max(0.0, min(1.0, float(value)))


@dataclass
class ScoreFeatures:
    semantic: float
    reading_depth: float
    suggestion: float
    explicit_feedback: float
    source_trust: float
    content_quality: float
    temporal_context: float
    novelty: float

    def as_dict(self) -> dict[str, float]:
        return {name: clamp01(getattr(self, name)) for name in SIGNALS}

    def vector(self) -> list[float]:
        values = self.as_dict()
        return [values[name] for name in SIGNALS]


def features_from_scores(scores: dict[str, float]) -> ScoreFeatures:
    return ScoreFeatures(**{name: clamp01(float(scores.get(name, 0.5))) for name in SIGNALS})


def history_without_target(history: list, item_id: object) -> list:
    return [row for row in history if getattr(row, "content_item_id", None) != item_id]


def predicted_reading_depth(
    history: list,
    *,
    item_id: object,
    source_id: object,
    length_bucket: str,
    prior: float = 0.5,
    prior_strength: float = 4.0,
) -> float:
    """Beta-shrunk completion for the same source and length, excluding this item."""
    usable = [
        row
        for row in history_without_target(history, item_id)
        if getattr(row, "read_completion_pct", None) is not None
        and getattr(row, "source_id", None) == source_id
        and getattr(row, "length_bucket", length_bucket) == length_bucket
    ]
    if not usable:
        return prior
    total = sum(float(row.read_completion_pct) for row in usable)
    mean = total / len(usable)
    weight = len(usable) / (len(usable) + prior_strength)
    return clamp01(weight * mean + (1 - weight) * prior)


def label_event(
    *,
    completion: float | None = None,
    rating: int | None = None,
    saved: bool = False,
    skipped: bool = False,
    reread: int = 0,
    viewed: bool = False,
) -> tuple[float, float] | None:
    """Return (label, confidence) or None when the event must not train.

    A skip counts only after the digest was actually viewed.
    """
    if skipped and not viewed:
        return None
    if rating is not None and rating > 0:
        return 1.0, 1.0
    if rating is not None and rating < 0:
        return 0.0, 1.0
    if skipped and viewed:
        return 0.0, 0.5
    if reread > 0:
        return 0.95, 0.9
    if saved:
        return 0.9, 0.8
    if completion is None:
        return None
    if completion < 0.2:
        return 0.1, 0.5
    if completion < 0.6:
        return 0.45, 0.6
    return min(1.0, 0.7 + 0.3 * completion), 0.8


def content_quality_score(
    *,
    word_count: int = 0,
    link_count: int = 0,
    citation_count: int = 0,
    has_code: bool = False,
    user_completion_for_bucket: float | None = None,
) -> float:
    length = 0.2 if word_count < 200 else 0.7 if word_count < 2000 else 0.85
    density = min(1.0, (link_count + citation_count) / 12)
    code = 0.15 if has_code else 0.0
    raw = clamp01(0.55 * length + 0.3 * density + code)
    if user_completion_for_bucket is None:
        return raw
    return clamp01(0.7 * raw + 0.3 * user_completion_for_bucket)


@dataclass
class BetaTrust:
    mean: float
    low: float
    high: float


def beta_trust(
    successes: float,
    failures: float,
    *,
    prior_success: float = 2.0,
    prior_failure: float = 2.0,
    age_days: float = 0.0,
    half_life_days: float = 90.0,
) -> BetaTrust:
    decay = 0.5 ** (max(age_days, 0.0) / half_life_days)
    alpha = prior_success + successes * decay
    beta = prior_failure + failures * decay
    mean = alpha / (alpha + beta)
    # A normal approximation of the Beta interval. New sources stay near the prior.
    variance = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))
    spread = 1.96 * math.sqrt(variance)
    return BetaTrust(clamp01(mean), clamp01(mean - spread), clamp01(mean + spread))


def long_term_weight(age_days: float, half_life_days: float = 120.0) -> float:
    return clamp01(0.5 ** (max(age_days, 0.0) / half_life_days))


def medium_term_weight(age_days: float) -> float:
    if age_days < 14 or age_days > 56:
        return 0.2
    return clamp01(1.0 - abs(age_days - 28) / 28)


def saturation_penalty(same_event_count: int, *, window_hours: float = 72.0) -> float:
    del window_hours
    if same_event_count <= 1:
        return 1.0
    return clamp01(1.0 / same_event_count)


def hour_histogram(open_hours: list[int]) -> list[float]:
    counts = [0] * 24
    for hour in open_hours:
        if 0 <= hour <= 23:
            counts[hour] += 1
    total = sum(counts) or 1
    return [count / total for count in counts]


def preferred_hour(open_hours: list[int], default: int = 7) -> int:
    if not open_hours:
        return default
    hist = hour_histogram(open_hours)
    return max(range(24), key=lambda hour: hist[hour])


def recency_fit(*, age_hours: float, user_prefers_fresh: bool) -> float:
    fresh = clamp01(math.exp(-age_hours / 72))
    if user_prefers_fresh:
        return fresh
    return clamp01(0.45 + 0.55 * (1 - fresh))


def temporal_score(
    *,
    published_at: datetime,
    now: datetime,
    same_event_count: int,
    user_prefers_fresh: bool,
) -> float:
    age_hours = max(0.0, (now - published_at).total_seconds() / 3600)
    age_days = age_hours / 24
    blended = (
        0.4 * long_term_weight(age_days)
        + 0.3 * medium_term_weight(age_days)
        + 0.3 * recency_fit(age_hours=age_hours, user_prefers_fresh=user_prefers_fresh)
    )
    return clamp01(blended * saturation_penalty(same_event_count))


def length_bucket(word_count: int | None) -> str:
    words = word_count or 0
    if words < 400:
        return "short"
    if words < 1500:
        return "medium"
    return "long"


def hours_between(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds() / 3600)


def within(moment: datetime, now: datetime, days: float) -> bool:
    return now - timedelta(days=days) <= moment <= now
