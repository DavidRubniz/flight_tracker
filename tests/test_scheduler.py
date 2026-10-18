from __future__ import annotations

from datetime import UTC, datetime, timedelta

from flight_tracker.services.scheduler import next_scan_time

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
SIX_HOURS = timedelta(hours=6)


def test_first_ever_scan_runs_soon() -> None:
    assert next_scan_time(None, SIX_HOURS, NOW) - NOW < timedelta(minutes=1)


def test_restart_does_not_rescan_before_interval() -> None:
    last = NOW - timedelta(hours=1)
    assert next_scan_time(last, SIX_HOURS, NOW) == last + SIX_HOURS


def test_overdue_scan_runs_soon() -> None:
    last = NOW - timedelta(days=2)
    assert next_scan_time(last, SIX_HOURS, NOW) - NOW < timedelta(minutes=1)
