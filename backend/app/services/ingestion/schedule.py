"""Per-feed poll interval. Time and randomness are arguments so tests stay fixed.

Rules (A1):
- no history: 1 hour
- otherwise the interval starts at half the median gap, clamped to 15 minutes..24 hours
- 304 or no new items: interval × 1.25, cap 24 hours
- new items: interval ÷ 1.5, floor 15 minutes, and the gap is remembered (last 20)
- next run is interval × uniform(0.9, 1.1), except errors, which are not jittered
- errors: 5 minutes × 2^n, cap 24 hours, and at least Retry-After
- 429 uses Retry-After when the server sends one
- 410 or seven days of continuous failure: dead
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

MIN_INTERVAL = 15 * 60
MAX_INTERVAL = 24 * 60 * 60
DEFAULT_INTERVAL = 60 * 60
_ERROR_BASE = 5 * 60
_DEAD_AFTER = timedelta(days=7)
_MAX_GAPS = 20


@dataclass
class ScheduleState:
    interval_seconds: int = DEFAULT_INTERVAL
    consecutive_errors: int = 0
    recent_gaps: list[int] = field(default_factory=list)
    status: str = "healthy"
    failure_since: datetime | None = None


def clamp_interval(seconds: float) -> int:
    return int(min(MAX_INTERVAL, max(MIN_INTERVAL, seconds)))


def initial_interval(recent_gaps: list[int]) -> int:
    if not recent_gaps:
        return DEFAULT_INTERVAL
    ordered = sorted(recent_gaps)
    median = ordered[len(ordered) // 2]
    return clamp_interval(median / 2)


def health_status(
    consecutive_errors: int,
    *,
    failure_since: datetime | None,
    now: datetime,
    gone: bool = False,
) -> str:
    if gone or (
        failure_since is not None and consecutive_errors > 0 and now - failure_since >= _DEAD_AFTER
    ):
        return "dead"
    if consecutive_errors <= 0:
        return "healthy"
    if consecutive_errors <= 2:
        return "degraded"
    return "failing"


def _jittered(now: datetime, interval: int, rng: random.Random) -> datetime:
    return now + timedelta(seconds=interval * rng.uniform(0.9, 1.1))


def on_quiet(
    state: ScheduleState, now: datetime, rng: random.Random
) -> tuple[ScheduleState, datetime]:
    """304 or a poll that produced no new items. The cap is 24 hours; no floor."""
    interval = int(min(MAX_INTERVAL, state.interval_seconds * 1.25))
    nxt = ScheduleState(
        interval_seconds=interval,
        consecutive_errors=0,
        recent_gaps=list(state.recent_gaps),
        status="healthy",
        failure_since=None,
    )
    return nxt, _jittered(now, interval, rng)


def on_new_items(
    state: ScheduleState,
    now: datetime,
    rng: random.Random,
    *,
    gap_seconds: int,
) -> tuple[ScheduleState, datetime]:
    gaps = [*state.recent_gaps, max(0, gap_seconds)][-_MAX_GAPS:]
    interval = int(max(MIN_INTERVAL, state.interval_seconds / 1.5))
    nxt = ScheduleState(
        interval_seconds=interval,
        consecutive_errors=0,
        recent_gaps=gaps,
        status="healthy",
        failure_since=None,
    )
    return nxt, _jittered(now, interval, rng)


def on_error(
    state: ScheduleState,
    now: datetime,
    *,
    retry_after: float | None = None,
    gone: bool = False,
) -> tuple[ScheduleState, datetime]:
    errors = state.consecutive_errors + 1
    since = state.failure_since or now
    status = health_status(errors, failure_since=since, now=now, gone=gone)
    backoff = min(_ERROR_BASE * (2**errors), MAX_INTERVAL)
    delay = max(backoff, float(retry_after or 0))
    nxt = ScheduleState(
        interval_seconds=state.interval_seconds,
        consecutive_errors=errors,
        recent_gaps=list(state.recent_gaps),
        status=status,
        failure_since=since,
    )
    return nxt, now + timedelta(seconds=delay)


def on_rate_limited(
    state: ScheduleState, now: datetime, retry_after: float
) -> tuple[ScheduleState, datetime]:
    """429. Honor Retry-After even when it is shorter than the error backoff."""
    errors = state.consecutive_errors + 1
    since = state.failure_since or now
    nxt = ScheduleState(
        interval_seconds=state.interval_seconds,
        consecutive_errors=errors,
        recent_gaps=list(state.recent_gaps),
        status=health_status(errors, failure_since=since, now=now),
        failure_since=since,
    )
    delay = retry_after if retry_after > 0 else min(_ERROR_BASE * (2**errors), MAX_INTERVAL)
    return nxt, now + timedelta(seconds=delay)


def politeness_delay(
    last_request_at: datetime | None, now: datetime, inflight: int
) -> float | None:
    """Seconds to wait before calling a host.

    None means the host is already at two in-flight requests and the caller
    must wait for one to finish. Otherwise the gap between requests is at least
    one second.
    """
    if inflight >= 2:
        return None
    if last_request_at is None:
        return 0.0
    return max(0.0, 1.0 - (now - last_request_at).total_seconds())


def apply_poll_result(
    source: object,
    *,
    now: datetime,
    rng: random.Random,
    new_items: bool = False,
    error: bool = False,
    gone: bool = False,
    retry_after: float | None = None,
    gap_seconds: int = 0,
) -> None:
    """Write the next schedule onto a source row."""
    previous = str(getattr(source, "feed_status", None) or "healthy")
    state = ScheduleState(
        interval_seconds=int(getattr(source, "poll_interval_seconds", None) or DEFAULT_INTERVAL),
        consecutive_errors=int(getattr(source, "fetch_error_count", None) or 0),
        recent_gaps=list(getattr(source, "recent_gap_seconds", None) or []),
        status=previous,
        failure_since=getattr(source, "failure_since", None),
    )
    if gone:
        nxt, when = on_error(state, now, gone=True)
    elif error and retry_after:
        nxt, when = on_rate_limited(state, now, retry_after)
    elif error:
        nxt, when = on_error(state, now, retry_after=retry_after)
    elif new_items:
        nxt, when = on_new_items(state, now, rng, gap_seconds=gap_seconds)
    else:
        nxt, when = on_quiet(state, now, rng)
    source.poll_interval_seconds = nxt.interval_seconds  # type: ignore[attr-defined]
    source.fetch_error_count = nxt.consecutive_errors  # type: ignore[attr-defined]
    source.recent_gap_seconds = nxt.recent_gaps  # type: ignore[attr-defined]
    source.feed_status = nxt.status  # type: ignore[attr-defined]
    source.failure_since = nxt.failure_since  # type: ignore[attr-defined]
    source.next_poll_at = when  # type: ignore[attr-defined]
    if nxt.status == "dead":
        source.is_active = False  # type: ignore[attr-defined]
        if previous != "dead":
            source.dead_notice_pending = True  # type: ignore[attr-defined]


def permanent_redirect_target(location: str | None, current_url: str) -> str | None:
    """Return the new URL when it is a different absolute http(s) URL."""
    if not location:
        return None
    from urllib.parse import urljoin, urlparse

    target = urljoin(current_url, location)
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if target.rstrip("/") == current_url.rstrip("/"):
        return None
    return target
