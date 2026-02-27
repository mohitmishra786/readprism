from __future__ import annotations

from datetime import time, datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest


def _make_user(tz: str = "UTC", preferred_hour: int = 7, preferred_minute: int = 0) -> MagicMock:
    user = MagicMock()
    user.timezone = tz
    user.digest_time_morning = time(preferred_hour, preferred_minute)
    return user


def test_is_digest_time_matches_when_in_window():
    """Should return True when current local time is within 15 minutes of preferred time."""
    from app.workers.tasks.build_digest import _is_digest_time_for_user
    import zoneinfo

    user = _make_user(tz="America/New_York", preferred_hour=8, preferred_minute=0)

    # Simulate 8:05 AM New York time
    ny_tz = zoneinfo.ZoneInfo("America/New_York")
    fake_now = datetime(2026, 1, 15, 8, 5, tzinfo=ny_tz)

    with patch("app.workers.tasks.build_digest.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        result = _is_digest_time_for_user(user)

    assert result is True


def test_is_digest_time_misses_when_outside_window():
    """Should return False when current local time is more than 15 minutes from preferred time."""
    from app.workers.tasks.build_digest import _is_digest_time_for_user
    import zoneinfo

    user = _make_user(tz="America/New_York", preferred_hour=8, preferred_minute=0)

    # Simulate 6:00 AM New York time (2 hours before preferred)
    ny_tz = zoneinfo.ZoneInfo("America/New_York")
    fake_now = datetime(2026, 1, 15, 6, 0, tzinfo=ny_tz)

    with patch("app.workers.tasks.build_digest.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        result = _is_digest_time_for_user(user)

    assert result is False


def test_is_digest_time_tolerates_invalid_timezone():
    """An unknown timezone string should fall back to UTC without crashing."""
    from app.workers.tasks.build_digest import _is_digest_time_for_user

    user = _make_user(tz="Invalid/Timezone", preferred_hour=0, preferred_minute=0)

    # Should not raise; just use UTC fallback
    try:
        result = _is_digest_time_for_user(user)
        assert isinstance(result, bool)
    except Exception as e:
        pytest.fail(f"_is_digest_time_for_user raised unexpectedly: {e}")
