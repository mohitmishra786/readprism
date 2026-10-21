"""Feature contract, signals, labels, trust, and temporal scales for ranking (#245).

All computed scores are normalized into [0.0, 1.0].
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

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
    """Clamp any numeric value into [0.0, 1.0], mapping NaNs and infinities to 0.5."""
    if math.isnan(value) or math.isinf(value):
        return 0.5
    return max(0.0, min(1.0, float(value)))


def label_event(
    *,
    completion: float | None = None,
    rating: int | None = None,
    saved: bool = False,
    skipped: bool = False,
    reread: int = 0,
    viewed: bool = False,
    reason: str | None = None,
    saved_unopened_days: float | None = None,
) -> tuple[float, float] | None:
    """Return (label, confidence) or None when the event should not train."""
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
    if saved and completion is not None and completion >= 0.9:
        return 1.0, 1.2
    if saved and saved_unopened_days is not None and saved_unopened_days >= 14:
        return 0.4, 0.3
    if saved:
        return 0.9, 0.8
    if completion is None:
        return None
    if completion < 0.2:
        return 0.1, 0.5
    if completion < 0.6:
        return 0.45, 0.6
    return min(1.0, 0.7 + 0.3 * completion), 0.8


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
    """Beta posterior trust estimate with exponential time decay."""
    decay = 0.5 ** (max(age_days, 0.0) / half_life_days)
    alpha = prior_success + successes * decay
    beta = prior_failure + failures * decay
    mean = alpha / (alpha + beta)
    variance = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))
    spread = 1.96 * math.sqrt(variance)
    return BetaTrust(clamp01(mean), clamp01(mean - spread), clamp01(mean + spread))


def long_term_weight(age_days: float, half_life_days: float = 120.0) -> float:
    """Exponential decay weight for long-term evergreen reading."""
    return clamp01(0.5 ** (max(age_days, 0.0) / half_life_days))


def medium_term_weight(age_days: float) -> float:
    """Triangular peak around 28 days for medium-term topical relevance."""
    if age_days < 14 or age_days > 56:
        return 0.2
    return clamp01(1.0 - abs(age_days - 28) / 28)


def saturation_penalty(same_event_count: int, *, window_hours: float = 72.0) -> float:
    """Penalty for multiple items reporting on the same event."""
    del window_hours
    if same_event_count <= 1:
        return 1.0
    return clamp01(1.0 / same_event_count)


def hour_histogram(open_hours: list[int]) -> list[float]:
    """Histogram of open timestamps across the 24 hours of the day."""
    counts = [0] * 24
    for hour in open_hours:
        if 0 <= hour <= 23:
            counts[hour] += 1
    total = sum(counts) or 1
    return [count / total for count in counts]


def preferred_hour(open_hours: list[int], default: int = 7) -> int:
    """Find the user's modal hour for reading."""
    if not open_hours:
        return default
    hist = hour_histogram(open_hours)
    return max(range(24), key=lambda hour: hist[hour])


def recency_fit(*, age_hours: float, user_prefers_fresh: bool) -> float:
    """Recency curve matching the user's fresh vs evergreen preference."""
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
    """Blended score combining long-term, medium-term, and fresh relevance."""
    age_hours = max(0.0, (now - published_at).total_seconds() / 3600)
    age_days = age_hours / 24
    blended = (
        0.4 * long_term_weight(age_days)
        + 0.3 * medium_term_weight(age_days)
        + 0.3 * recency_fit(age_hours=age_hours, user_prefers_fresh=user_prefers_fresh)
    )
    return clamp01(blended * saturation_penalty(same_event_count))


def length_bucket(word_count: int | None) -> str:
    """Bucket word counts into short, medium, or long."""
    words = word_count or 0
    if words < 400:
        return "short"
    if words < 1500:
        return "medium"
    return "long"
