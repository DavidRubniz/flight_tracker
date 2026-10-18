"""Background scheduling of periodic scans (APScheduler)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from flight_tracker.models import AppSettings
from flight_tracker.services.tracker import PriceTracker

logger = logging.getLogger(__name__)

_JOB_ID = "scan-all"
_FIRST_RUN_DELAY = timedelta(seconds=5)


class ScanScheduler:
    def __init__(self, tracker: PriceTracker) -> None:
        self._tracker = tracker
        self._scheduler = AsyncIOScheduler()

    def start(self, settings: AppSettings) -> None:
        self._scheduler.start()
        self.apply(settings, run_soon=True)

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def apply(self, settings: AppSettings, *, run_soon: bool = False) -> None:
        """(Re)configure the job from the current settings."""
        if self._scheduler.get_job(_JOB_ID):
            self._scheduler.remove_job(_JOB_ID)
        if not settings.scheduler_enabled:
            logger.info("Automatic scanning disabled")
            return
        first_run = datetime.now().astimezone() + (
            _FIRST_RUN_DELAY if run_soon else timedelta(hours=settings.scan_interval_hours)
        )
        self._scheduler.add_job(
            self._tracker.scan_all,
            IntervalTrigger(hours=settings.scan_interval_hours),
            id=_JOB_ID,
            next_run_time=first_run,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=600,
        )
        logger.info("Automatic scan every %.2f hours", settings.scan_interval_hours)

    @property
    def next_run(self) -> datetime | None:
        job = self._scheduler.get_job(_JOB_ID)
        return job.next_run_time if job else None
