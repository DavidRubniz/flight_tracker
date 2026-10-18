from __future__ import annotations

import httpx

from flight_tracker.database import Database
from flight_tracker.models import DestinationCreate, FlightOffer, SearchQuery, Segment
from flight_tracker.notifications import Notification
from flight_tracker.providers import FlightProvider, ProviderAuthError, ProviderError
from flight_tracker.services.tracker import PriceTracker


class FakeProvider(FlightProvider):
    name = "fake"

    def __init__(self, price: float = 100, error: Exception | None = None) -> None:
        super().__init__(httpx.AsyncClient())
        self.price = price
        self.error = error
        self.calls: list[SearchQuery] = []

    async def search(self, query: SearchQuery) -> list[FlightOffer]:
        self.calls.append(query)
        if self.error:
            raise self.error
        return [
            FlightOffer(
                provider=self.name,
                destination_code=query.destination,
                price=self.price,
                currency="USD",
                airlines=["X"],
                stops=0,
                outbound=[Segment(origin="TLV", destination=query.destination, airline="X")],
                depart_date=query.depart_date,
                return_date=query.return_date,
            )
        ]


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[Notification] = []

    async def dispatch(self, notification: Notification) -> dict[str, str]:
        self.sent.append(notification)
        return {"fake": "ok"}


def _tracker(db: Database, provider: FlightProvider, notifier: FakeNotifier) -> PriceTracker:
    return PriceTracker(db, provider, notifier, origin="TLV", currency="USD")  # type: ignore[arg-type]


def _only(db: Database, code: str, target: float | None) -> int:
    """Replace the seeded destinations with a single one."""
    for destination in db.list_destinations():
        db.delete_destination(destination.id)
    return db.add_destination(DestinationCreate(code=code, target_price=target)).id


async def test_scan_records_and_alerts_once(db: Database) -> None:
    dest_id = _only(db, "ATH", target=150)
    notifier = FakeNotifier()
    tracker = _tracker(db, FakeProvider(price=120), notifier)

    await tracker.scan_all()
    await tracker.scan_all()  # same price again -> suppressed by the cooldown

    assert len(db.price_history(dest_id)) == 2
    assert len(notifier.sent) == 1
    assert db.list_alerts()[0].kind == "target"


async def test_region_expands_to_all_airports(db: Database) -> None:
    _only(db, "USA", target=None)
    provider = FakeProvider()
    await _tracker(db, provider, FakeNotifier()).scan_all()
    assert len(provider.calls) == 6 * len(db.get_settings().date_offsets_days)


async def test_provider_errors_are_reported_not_raised(db: Database) -> None:
    dest_id = _only(db, "ATH", target=None)
    tracker = _tracker(db, FakeProvider(error=ProviderError("down")), FakeNotifier())
    await tracker.scan_all()
    assert tracker.status.errors
    assert db.price_history(dest_id) == []


async def test_auth_error_aborts_scan(db: Database) -> None:
    _only(db, "ATH", target=None)
    tracker = _tracker(db, FakeProvider(error=ProviderAuthError("bad key")), FakeNotifier())
    await tracker.scan_all()
    assert tracker.status.errors == ["bad key"]
    assert not tracker.status.running
