"""Scan engine: queries the provider for every tracked destination, stores
results and raises alerts."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from datetime import date, timedelta

from flight_tracker.database import Database, utcnow
from flight_tracker.models import AppSettings, Destination, FlightOffer, ScanStatus, SearchQuery
from flight_tracker.notifications import Notification, NotificationDispatcher
from flight_tracker.providers import FlightProvider, ProviderAuthError, ProviderError
from flight_tracker.regions import airports_for, display_name
from flight_tracker.services.pricing import evaluate_price, is_repeat_alert

logger = logging.getLogger(__name__)

MAX_CONCURRENT_REQUESTS = 3
OFFERS_KEPT_PER_SCAN = 15


class ScanAbortedError(Exception):
    """Raised when a scan cannot continue at all (e.g. invalid API credentials)."""


class PriceTracker:
    def __init__(
        self,
        db: Database,
        provider: FlightProvider,
        notifier: NotificationDispatcher,
        *,
        origin: str,
        currency: str,
    ) -> None:
        self._db = db
        self._provider = provider
        self._notifier = notifier
        self._origin = origin
        self._currency = currency
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self.status = ScanStatus(provider=provider.name)

    @property
    def is_running(self) -> bool:
        return self._lock.locked()

    # ------------------------------------------------------------------ public API

    async def scan_all(self) -> None:
        await self._run(self._db.list_destinations(only_enabled=True))

    async def scan_one(self, destination_id: int) -> None:
        destination = self._db.get_destination(destination_id)
        if destination is not None:
            await self._run([destination])

    # ------------------------------------------------------------------ internals

    async def _run(self, destinations: list[Destination]) -> None:
        if self._lock.locked():
            logger.info("Scan already in progress - skipping")
            return
        async with self._lock:
            settings = self._db.get_settings()
            self.status.running = True
            self.status.errors = []
            self.status.last_started = utcnow()
            try:
                for index, destination in enumerate(destinations, start=1):
                    self.status.progress = f"{index}/{len(destinations)} · {destination.name}"
                    await self._scan_destination(destination, settings)
            except ScanAbortedError as exc:
                logger.error("Scan aborted: %s", exc)
                self.status.errors.append(str(exc))
            finally:
                self.status.running = False
                self.status.progress = ""
                self.status.last_finished = utcnow()

    def _build_queries(self, destination: Destination, settings: AppSettings) -> Iterable[SearchQuery]:
        today = date.today()
        for airport in airports_for(destination.code):
            for offset in settings.date_offsets_days:
                depart = today + timedelta(days=offset)
                yield SearchQuery(
                    origin=self._origin,
                    destination=airport,
                    depart_date=depart,
                    return_date=depart + timedelta(days=destination.trip_nights)
                    if destination.trip_nights
                    else None,
                    max_stops=destination.max_stops,
                    currency=self._currency,
                )

    async def _search(self, query: SearchQuery) -> list[FlightOffer]:
        async with self._semaphore:
            return await self._provider.search(query)

    async def _scan_destination(self, destination: Destination, settings: AppSettings) -> None:
        queries = list(self._build_queries(destination, settings))
        results = await asyncio.gather(*(self._search(q) for q in queries), return_exceptions=True)

        offers: dict[tuple[str, str, str, float], FlightOffer] = {}
        failures = 0
        for query, result in zip(queries, results, strict=True):
            if isinstance(result, ProviderAuthError):
                raise ScanAbortedError(str(result)) from result
            if isinstance(result, ProviderError):
                failures += 1
                logger.warning(
                    "%s → %s on %s failed: %s", query.origin, query.destination, query.depart_date, result
                )
                continue
            if isinstance(result, BaseException):
                failures += 1
                logger.exception("Unexpected error for %s", query.destination, exc_info=result)
                continue
            for offer in result:
                offers.setdefault(offer.dedupe_key, offer)

        if failures:
            self.status.errors.append(f"{destination.name}: {failures}/{len(queries)} חיפושים נכשלו")
        if not offers:
            logger.info("No offers found for %s", destination.code)
            return

        ranked = sorted(offers.values(), key=lambda o: o.price)[:OFFERS_KEPT_PER_SCAN]
        # Compute the baseline *before* storing the new snapshot.
        average, samples = self._db.average_price(destination.id)
        self._db.record_scan(destination.id, ranked)
        await self._maybe_alert(destination, ranked[0], average, samples, settings)

    async def _maybe_alert(
        self,
        destination: Destination,
        best: FlightOffer,
        average: float | None,
        samples: int,
        settings: AppSettings,
    ) -> None:
        decision = evaluate_price(
            best.price,
            target_price=destination.target_price,
            average_price=average,
            sample_size=samples,
            deal_drop_percent=settings.deal_drop_percent,
        )
        if decision is None:
            return
        if is_repeat_alert(
            best.price, self._db.last_alert_price(destination.id, settings.alert_cooldown_hours)
        ):
            return

        route = f"{self._origin} → {best.destination_code} ({display_name(best.destination_code)})"
        stops = "ישירה" if best.stops == 0 else f"{best.stops} עצירות דרך {', '.join(best.connections)}"
        dates = best.depart_date.strftime("%d/%m/%Y")
        if best.return_date:
            dates += f" – {best.return_date.strftime('%d/%m/%Y')}"
        title = f"✈ {destination.name}: {best.price:,.0f} {best.currency}"
        body = f"{decision.reason}\n{route}\n{dates} · {stops}\n{', '.join(best.airlines)}"

        self._db.add_alert(destination.id, decision.kind, best.price, best.currency, body)
        await self._notifier.dispatch(Notification(title=title, body=body, url=best.booking_url))
