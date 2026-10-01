"""Digest length personalization (UX-02).

The spec formula: N = clamp(1.25 · EMA(items opened per digest), 5, 30),
unless the user explicitly overrode the length — an explicit choice is never
clobbered by the learner.
"""

from __future__ import annotations

LENGTH_FLOOR = 5
LENGTH_CAP = 30
OPEN_FACTOR = 1.25
EMA_ALPHA = 0.3
EMA_WINDOW = 10


def ema_opened_per_digest(counts: list[float], alpha: float = EMA_ALPHA) -> float | None:
    """Exponential moving average over per-digest opened counts, oldest first.

    Returns None when there is no history (brand-new user).
    """
    if not counts:
        return None
    ema = float(counts[0])
    for count in counts[1:]:
        ema = alpha * float(count) + (1 - alpha) * ema
    return ema


def target_digest_length(
    ema: float | None,
    *,
    current: int,
    locked: bool,
    floor: int = LENGTH_FLOOR,
    cap: int = LENGTH_CAP,
    factor: float = OPEN_FACTOR,
) -> int:
    """Effective digest length. A locked (explicit) value always wins."""
    if locked or ema is None:
        return current
    return max(floor, min(cap, round(factor * ema)))
