"""Composition root: wires every service together once, at startup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, Request

from flight_tracker.config import Config
from flight_tracker.database import Database
from flight_tracker.notifications import NotificationDispatcher
from flight_tracker.providers import FlightProvider, create_provider
from flight_tracker.services.scheduler import ScanScheduler
from flight_tracker.services.tracker import PriceTracker


@dataclass(slots=True)
class Container:
    config: Config
    db: Database
    http: httpx.AsyncClient
    provider: FlightProvider
    notifier: NotificationDispatcher
    tracker: PriceTracker
    scheduler: ScanScheduler

    @classmethod
    def build(cls, config: Config) -> Container:
        db = Database(config.db_path)
        http = httpx.AsyncClient(
            timeout=httpx.Timeout(config.http_timeout_seconds),
            headers={"User-Agent": "flight-tracker/1.0"},
        )
        provider = create_provider(config, http)
        notifier = NotificationDispatcher(config, http, db.get_settings)
        tracker = PriceTracker(db, provider, notifier, origin=config.origin_airport, currency=config.currency)
        scheduler = ScanScheduler(tracker, db.last_scan_at)
        return cls(config, db, http, provider, notifier, tracker, scheduler)

    def start(self) -> None:
        self.scheduler.start(self.db.get_settings())

    async def aclose(self) -> None:
        self.scheduler.shutdown()
        await self.http.aclose()
        self.db.close()


def _get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(_get_container)]
