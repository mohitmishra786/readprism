"""Flaky YouTube channel feeds (#240)."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from app.models.feed import Feed
from app.models.source import Source
from app.services.ingestion.feeds import mirror
from app.services.ingestion.schedule import PLATFORM_OUTAGE, apply_poll_result, is_youtube_feed

YT = "https://www.youtube.com/feeds/videos.xml?channel_id=UC0123456789abcdefghijk"
START = datetime(2026, 10, 20, 8, tzinfo=UTC)


def _feed(url: str) -> Feed:
    return Feed(
        key=url,
        url=url,
        feed_url=url,
        is_active=True,
        feed_status="healthy",
        fetch_error_count=0,
        poll_interval_seconds=3600,
        recent_gap_seconds=[],
    )


def _outage(feed: Feed, hours: float, *, codes=(500, 404, 410, 503)) -> list[str]:
    """Poll whenever the schedule says, failing with outage codes, for `hours`."""
    rng = random.Random(1)
    now, end, statuses, i = START, START + timedelta(hours=hours), [], 0
    while now < end:
        code = codes[i % len(codes)]
        apply_poll_result(feed, now=now, rng=rng, error=code != 410, gone=code == 410)
        statuses.append(feed.feed_status)
        now = feed.next_poll_at
        i += 1
    return statuses


def test_recognises_youtube_channel_feeds():
    assert is_youtube_feed(YT)
    assert is_youtube_feed("https://youtube.com/feeds/videos.xml?playlist_id=PL1")
    assert not is_youtube_feed("https://www.youtube.com/@somechannel")
    assert not is_youtube_feed("https://example.com/feeds/videos.xml")


def test_six_hour_outage_never_marks_dead_or_sends_notices():
    feed = _feed(YT)
    subscriber = Source(url=YT, feed_url=YT, is_active=True, dead_notice_pending=False)
    statuses = _outage(feed, 6)
    mirror(feed, [subscriber])
    assert len(statuses) >= 4  # it kept retrying through the outage
    assert set(statuses) == {PLATFORM_OUTAGE}
    assert feed.is_active and not getattr(feed, "dead_notice_pending", False)
    assert subscriber.is_active and not subscriber.dead_notice_pending
    # Retries stay frequent enough to recover within ~3 hours.
    assert feed.next_poll_at - START <= timedelta(hours=6 + 3, minutes=20)

    apply_poll_result(
        feed, now=feed.next_poll_at, rng=random.Random(2), new_items=True, gap_seconds=3600
    )
    assert feed.feed_status == "healthy" and feed.fetch_error_count == 0


def test_a_channel_failing_for_30_days_is_finally_treated_as_gone():
    feed = _feed(YT)
    _outage(feed, 24 * 31, codes=(404,))
    assert feed.feed_status == "dead" and feed.is_active is False


def test_other_feeds_are_unchanged():
    url = "https://blog.example.com/feed.xml"
    gone = _feed(url)
    apply_poll_result(gone, now=START, rng=random.Random(3), gone=True)
    assert gone.feed_status == "dead"  # 410 still means gone elsewhere
    flaky = _feed(url)
    statuses = _outage(flaky, 6, codes=(500,))
    assert statuses[-1] == "failing" and flaky.is_active
