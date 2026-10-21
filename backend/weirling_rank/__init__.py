"""weirling-rank: Reusable, explainable recommendation ranker for feeds and reading digests (#245).

Zero external database or network dependencies. Requires only Python and NumPy.
"""

from __future__ import annotations

from weirling_rank.contract import (
    SIGNALS,
    BetaTrust,
    beta_trust,
    clamp01,
    hour_histogram,
    label_event,
    length_bucket,
    long_term_weight,
    medium_term_weight,
    preferred_hour,
    recency_fit,
    saturation_penalty,
    temporal_score,
)
from weirling_rank.ranker import (
    BRIDGE_EDGE_WEIGHT,
    CLUSTER_DISTANCE,
    HISTORY_LIMIT,
    KNN,
    MAX_INTEREST_VECTORS,
    NEUTRAL,
    NOVELTY_WINDOW_DAYS,
    RECENT_EVENT_HOURS,
    SAME_EVENT_COSINE,
    average_linkage,
    build_interests,
    rank_candidates,
    score_candidates,
)
from weirling_rank.types import (
    Candidate,
    FeedState,
    HistoryRow,
    Interest,
    Scored,
    UserRankingState,
)

try:
    # The release workflow sets the version at build time from the next
    # weirling-rank-v* tag; inside the app (not pip-installed) it's "0.0.0".
    from importlib.metadata import PackageNotFoundError, version

    __version__ = version("weirling-rank")
except PackageNotFoundError:  # pragma: no cover - running from source
    __version__ = "0.0.0"
__all__ = [
    "BRIDGE_EDGE_WEIGHT",
    "CLUSTER_DISTANCE",
    "HISTORY_LIMIT",
    "KNN",
    "MAX_INTEREST_VECTORS",
    "NEUTRAL",
    "NOVELTY_WINDOW_DAYS",
    "RECENT_EVENT_HOURS",
    "SAME_EVENT_COSINE",
    "SIGNALS",
    "BetaTrust",
    "Candidate",
    "FeedState",
    "HistoryRow",
    "Interest",
    "Scored",
    "UserRankingState",
    "average_linkage",
    "beta_trust",
    "build_interests",
    "clamp01",
    "hour_histogram",
    "label_event",
    "length_bucket",
    "long_term_weight",
    "medium_term_weight",
    "preferred_hour",
    "rank_candidates",
    "recency_fit",
    "saturation_penalty",
    "score_candidates",
    "temporal_score",
]
