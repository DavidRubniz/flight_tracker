"""Assembles the read-model shown on the dashboard."""

from __future__ import annotations

from flight_tracker.database import Database
from flight_tracker.models import DashboardRow, Destination, StoredOffer
from flight_tracker.services.pricing import price_trend

HISTORY_DAYS = 30


def build_row(db: Database, destination: Destination, best_offers: dict[int, StoredOffer]) -> DashboardRow:
    history = db.price_history(destination.id, days=HISTORY_DAYS)
    lowest = db.lowest_price(destination.id)
    average, _ = db.average_price(destination.id, days=HISTORY_DAYS)
    trend, change = price_trend(history)
    current = history[-1].price if history else None
    return DashboardRow(
        destination=destination,
        current_price=current,
        lowest_price=lowest[0] if lowest else None,
        lowest_seen_at=lowest[1] if lowest else None,
        average_price=average,
        change_percent=change,
        trend=trend,
        history=history,
        last_checked=history[-1].at if history else None,
        best_offer=best_offers.get(destination.id),
        insights=db.latest_insights(destination.id),
        below_target=bool(
            current is not None and destination.target_price and current <= destination.target_price
        ),
    )


def build_dashboard(db: Database) -> list[DashboardRow]:
    best_offers: dict[int, StoredOffer] = {}
    for offer in db.latest_offers(limit=1000):  # cheapest first
        best_offers.setdefault(offer.destination_id, offer)
    return [build_row(db, d, best_offers) for d in db.list_destinations()]
