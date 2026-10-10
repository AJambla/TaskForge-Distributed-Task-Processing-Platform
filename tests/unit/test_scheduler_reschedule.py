"""Unit tests for scheduler calculation and rescheduling logic."""
from datetime import datetime, timezone

from app.scheduler.main import _next_occurrence


def test_next_occurrence_croniter():
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    # Every hour at minute 0
    next_time = _next_occurrence(base, "0 * * * *")
    assert next_time is not None
    assert next_time == datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc)


def test_next_occurrence_daily():
    base = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    # Daily at 9am
    next_time = _next_occurrence(base, "0 9 * * *")
    assert next_time is not None
    assert next_time == datetime(2026, 1, 2, 9, 0, 0, tzinfo=timezone.utc)


def test_next_occurrence_invalid():
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    next_time = _next_occurrence(base, "not-a-cron-expression")
    assert next_time is None
