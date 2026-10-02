"""Reason-tag → learning-signal mapping (UX-06).

One table, used by the feedback endpoint, the label builder, and the docs
(docs/feedback-mapping.md). Every tag maps to:

- a behavior label (y, c) per the A4 table — used by training, and
- optional side effects on the interest graph (cluster weight) or the
  source trust prior.

UI controls that map to *other* existing endpoints (not this table):
- "Snooze topic"  → POST /feedback/adjust-interests {action: suppress,
  duration_days: 14}
- "Mute source"   → PATCH /sources/{id} {is_active: false}
- "More/Less like this" → POST /feedback/adjust-interests {action:
  boost|suppress} on the item's top cluster.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReasonEffect:
    label_y: float
    confidence: float
    # Multiplicative/absolute change applied to the interest node weight of
    # the item's top cluster. 0.0 means "no cluster change".
    cluster_weight_delta: float = 0.0
    # Absolute change applied to sources.trust_weight. 0.0 means none.
    source_trust_delta: float = 0.0


REASON_EFFECTS: dict[str, ReasonEffect] = {
    # A4: "too basic"/"already knew" -> y 0.35, c 0.8, raise depth level for
    # the cluster. The depth level itself is carried by the label; the
    # cluster is nudged down so shallower items surface less.
    "too_basic": ReasonEffect(label_y=0.35, confidence=0.8, cluster_weight_delta=-0.10),
    "already_knew": ReasonEffect(label_y=0.35, confidence=0.8, cluster_weight_delta=-0.10),
    # A4: "off-topic" -> y 0.0, c 1.0, weaken that cluster link.
    "off_topic": ReasonEffect(label_y=0.0, confidence=1.0, cluster_weight_delta=-0.20),
    # Legacy spelling the first FeedbackBar shipped with; same behavior.
    "too_tangential": ReasonEffect(label_y=0.0, confidence=1.0, cluster_weight_delta=-0.20),
    # Depth mismatch is a calibration signal, not a cluster rejection.
    "wrong_depth": ReasonEffect(label_y=0.45, confidence=0.6),
    # Clickbait is a source-quality failure, not an interest miss.
    "clickbait": ReasonEffect(label_y=0.20, confidence=0.8, source_trust_delta=-0.10),
}


def reason_effect(reason: str | None) -> ReasonEffect | None:
    """Return the mapped effect for a reason tag, or None if unmapped."""
    if not reason:
        return None
    return REASON_EFFECTS.get(reason)
