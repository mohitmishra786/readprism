"""Simulated-clock tests for the feed poll scheduler."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest

from app.services.ingestion.schedule import (
    DEFAULT_INTERVAL,
    MAX_INTERVAL,
    MIN_INTERVAL,
    ScheduleState,
    health_status,
    initial_interval,
    on_error,
    on_new_items,
    on_quiet,
    on_rate_limited,
    permanent_redirect_target,
)

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def test_initial_interval_defaults_to_one_hour():
    assert initial_interval([]) == DEFAULT_INTERVAL


def test_initial_interval_is_half_the_median_gap_clamped():
    assert initial_interval([3600, 7200, 10800]) == 3600  # median 7200 / 2
    assert initial_interval([60, 60, 60]) == MIN_INTERVAL
    assert initial_interval([7 * 24 * 3600]) == MAX_INTERVAL


def test_quiet_poll_grows_the_interval_with_jitter():
    rng = random.Random(1)
    state = ScheduleState(interval_seconds=3600)
    nxt, when = on_quiet(state, NOW, rng)
    assert nxt.interval_seconds == 4500
    assert nxt.consecutive_errors == 0
    assert nxt.status == "healthy"
    delta = (when - NOW).total_seconds()
    assert 4500 * 0.9 <= delta <= 4500 * 1.1


def test_quiet_poll_caps_at_24_hours():
    nxt, _ = on_quiet(ScheduleState(interval_seconds=MAX_INTERVAL), NOW, random.Random(0))
    assert nxt.interval_seconds == MAX_INTERVAL


def test_new_items_shrink_the_interval_and_record_the_gap():
    rng = random.Random(2)
    state = ScheduleState(interval_seconds=3600, recent_gaps=[100])
    nxt, when = on_new_items(state, NOW, rng, gap_seconds=1800)
    assert nxt.interval_seconds == 2400
    assert nxt.recent_gaps == [100, 1800]
    assert nxt.status == "healthy"
    delta = (when - NOW).total_seconds()
    assert 2400 * 0.9 <= delta <= 2400 * 1.1


def test_new_items_floor_at_15_minutes_and_keep_20_gaps():
    state = ScheduleState(interval_seconds=MIN_INTERVAL, recent_gaps=list(range(20)))
    nxt, _ = on_new_items(state, NOW, random.Random(0), gap_seconds=50)
    assert nxt.interval_seconds == MIN_INTERVAL
    assert len(nxt.recent_gaps) == 20
    assert nxt.recent_gaps[-1] == 50
    assert 0 not in nxt.recent_gaps


def test_errors_back_off_without_jitter():
    state = ScheduleState()
    first, when1 = on_error(state, NOW)
    assert first.consecutive_errors == 1
    assert first.status == "degraded"
    assert when1 - NOW == timedelta(minutes=10)  # 5 * 2^1

    second, when2 = on_error(first, when1)
    assert second.consecutive_errors == 2
    assert second.status == "degraded"
    assert when2 - when1 == timedelta(minutes=20)

    third, _ = on_error(second, when2)
    assert third.status == "failing"
    assert third.consecutive_errors == 3


def test_retry_after_extends_the_backoff():
    _, when = on_error(ScheduleState(), NOW, retry_after=3600)
    assert when - NOW == timedelta(hours=1)


def test_rate_limit_honors_retry_after():
    limited, when = on_rate_limited(ScheduleState(), NOW, retry_after=90)
    assert when - NOW == timedelta(seconds=90)
    assert limited.consecutive_errors == 1
    _, later = on_rate_limited(ScheduleState(), NOW, retry_after=7200)
    assert later - NOW == timedelta(hours=2)


def test_gone_and_week_long_failure_are_dead():
    dead, _ = on_error(ScheduleState(), NOW, gone=True)
    assert dead.status == "dead"
    week = NOW + timedelta(days=7)
    assert health_status(3, failure_since=NOW, now=week) == "dead"
    assert health_status(3, failure_since=NOW, now=NOW + timedelta(days=6)) == "failing"


def test_same_host_waits_out_the_one_second_gap():
    from app.services.ingestion.schedule import politeness_delay

    assert politeness_delay(None, NOW, 0) == 0
    assert politeness_delay(NOW, NOW + timedelta(milliseconds=200), 0) == pytest.approx(
        0.8, abs=0.01
    )
    assert politeness_delay(NOW, NOW + timedelta(seconds=2), 0) == 0
    assert politeness_delay(NOW, NOW, 2) is None


def test_permanent_redirect_rewrites_only_a_different_http_url():
    assert (
        permanent_redirect_target("https://feeds.example.com/new", "https://old.example.com/rss")
        == "https://feeds.example.com/new"
    )
    assert (
        permanent_redirect_target("/rss.xml", "https://example.com/blog")
        == "https://example.com/rss.xml"
    )
    assert permanent_redirect_target("https://example.com/rss", "https://example.com/rss") is None
    assert permanent_redirect_target("javascript:alert(1)", "https://example.com/rss") is None
