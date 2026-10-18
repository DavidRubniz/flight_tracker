"""Background scheduling of periodic scans (APScheduler)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from flight_tracker.models import AppSettings
from flight_tracker.services.tracker import PriceTracker

logger = logging.getLogger(__name__)

_JOB_ID = "scan-all"
_MIN_DELAY = timedelta(seconds=5)


def next_scan_time(last_scan: datetime | None, interval: timedelta, now: datetime) -> datetime:
    """Next run = last scan + interval, but never in the past.

    Basing it on the last *stored* scan means restarting the app does not trigger
    a fresh scan (and burn paid API quota) every time.
    """
    earliest = now + _MIN_DELAY
    if last_scan is None:
        return earliest
    return max(last_scan + interval, earliest)


class ScanScheduler:
    def __init__(self, tracker: PriceTracker, last_scan_provider: Callable[[], datetime | None]) -> None:
        self._tracker = tracker
        self._last_scan_provider = last_scan_provider
        self._scheduler = AsyncIOScheduler()

    def start(self, settings: AppSettings) -> None:
        self._scheduler.start()
        self.apply(settings)

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def apply(self, settings: AppSettings) -> None:
        """(Re)configure the job from the current settings."""
        if self._scheduler.get_job(_JOB_ID):
            self._scheduler.remove_job(_JOB_ID)
        if not settings.scheduler_enabled:
            logger.info("Automatic scanning disabled")
            return
        interval = timedelta(hours=settings.scan_interval_hours)
        first_run = next_scan_time(self._last_scan_provider(), interval, datetime.now().astimezone())
        self._scheduler.add_job(
            self._tracker.scan_all,
            IntervalTrigger(hours=settings.scan_interval_hours),
            id=_JOB_ID,
            next_run_time=first_run,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=600,
        )
        logger.info(
            "Automatic scan every %.2f hours, next at %s",
            settings.scan_interval_hours,
            first_run.strftime("%Y-%m-%d %H:%M"),
        )

    @property
    def next_run(self) -> datetime | None:
        job = self._scheduler.get_job(_JOB_ID)
        return job.next_run_time if job else None
