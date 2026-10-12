"""Unit tests for timezone-aware cron scheduling (IMP-23)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.scheduler.main import _next_occurrence


def test_next_occurrence_utc_default():
    # 2026-10-11 12:00:00 UTC, every day at 14:00
    base = datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)
    next_run = _next_occurrence(base, "0 14 * * *", tz_name="UTC")
    assert next_run is not None
    assert next_run == datetime(2026, 10, 11, 14, 0, 0, tzinfo=timezone.utc)


def test_next_occurrence_with_specific_timezone():
    # In New York (EDT, UTC-4 in October)
    # Cron at 9:00 AM EDT corresponds to 13:00 UTC
    base = datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc)  # 6:00 AM EDT
    next_run = _next_occurrence(base, "0 9 * * *", tz_name="America/New_York")
    assert next_run is not None
    # 9:00 AM EDT -> 13:00 UTC
    assert next_run == datetime(2026, 10, 11, 13, 0, 0, tzinfo=timezone.utc)


def test_next_occurrence_tokyo_timezone():
    # In Asia/Tokyo (JST, UTC+9)
    # Cron at 10:00 AM JST corresponds to 01:00 UTC
    base = datetime(2026, 10, 11, 0, 0, 0, tzinfo=timezone.utc)  # 9:00 AM JST
    next_run = _next_occurrence(base, "0 10 * * *", tz_name="Asia/Tokyo")
    assert next_run is not None
    # 10:00 AM JST -> 01:00 UTC
    assert next_run == datetime(2026, 10, 11, 1, 0, 0, tzinfo=timezone.utc)


def test_next_occurrence_invalid_tz_falls_back_to_utc():
    base = datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)
    next_run = _next_occurrence(base, "0 15 * * *", tz_name="Invalid/Timezone")
    assert next_run is not None
    assert next_run == datetime(2026, 10, 11, 15, 0, 0, tzinfo=timezone.utc)
