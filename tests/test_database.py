from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from flight_tracker.database import Database
from flight_tracker.models import (
    AppSettings,
    DestinationCreate,
    DestinationUpdate,
    FlightOffer,
    PriceInsights,
    Segment,
)


def _offer(price: float, code: str = "ATH") -> FlightOffer:
    return FlightOffer(
        provider="test",
        destination_code=code,
        price=price,
        currency="USD",
        airlines=["Aegean"],
        stops=0,
        outbound=[Segment(origin="TLV", destination=code, airline="Aegean", flight_number="A3929")],
        depart_date=date(2026, 12, 1),
    )


def test_seeds_default_destinations(db: Database) -> None:
    assert len(db.list_destinations()) > 0


def test_destination_crud(db: Database) -> None:
    created = db.add_destination(DestinationCreate(code="mxp", target_price=150))
    assert created.code == "MXP"
    assert created.name == "מילאנו"

    updated = db.update_destination(created.id, DestinationUpdate(clear_target_price=True, one_way=True))
    assert updated is not None
    assert updated.target_price is None
    assert updated.trip_nights is None

    limited = db.update_destination(created.id, DestinationUpdate(max_duration_hours=12))
    assert limited is not None
    assert limited.max_duration_hours == 12
    assert limited.trip_nights is None  # unrelated fields keep their values
    cleared = db.update_destination(created.id, DestinationUpdate(clear_max_duration=True))
    assert cleared is not None
    assert cleared.max_duration_hours is None

    assert db.delete_destination(created.id)
    assert db.get_destination(created.id) is None


def test_record_scan_tracks_history_and_lowest(db: Database) -> None:
    dest = db.add_destination(DestinationCreate(code="MXP"))
    db.record_scan(dest.id, [_offer(300, "MXP"), _offer(350, "MXP")])
    db.record_scan(dest.id, [_offer(250, "MXP")])

    assert [p.price for p in db.price_history(dest.id)] == [300, 250]
    lowest = db.lowest_price(dest.id)
    assert lowest is not None
    assert lowest[0] == 250
    # only offers from the latest snapshot are returned
    assert [o.price for o in db.latest_offers(dest.id)] == [250]


def test_settings_roundtrip(db: Database) -> None:
    db.save_settings(AppSettings(scan_interval_hours=2, date_offsets_days=[60, 10, 10]))
    loaded = db.get_settings()
    assert loaded.scan_interval_hours == 2
    assert loaded.date_offsets_days == [10, 60]


def test_migration_adds_columns_to_an_existing_database(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:  # a snapshots table from before price insights existed
        conn.execute(
            "CREATE TABLE snapshots (id INTEGER PRIMARY KEY, destination_id INTEGER NOT NULL, "
            "checked_at TEXT NOT NULL, min_price REAL NOT NULL, currency TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO snapshots VALUES (1, 1, '2026-01-01T00:00:00+00:00', 99, 'USD')")
    conn.close()

    db = Database(path)
    try:
        assert db.latest_insights(1) is None  # old rows keep working
        dest = db.add_destination(DestinationCreate(code="MXP"))
        insights = PriceInsights(price_level="typical", typical_low=200, typical_high=300)
        db.record_scan(dest.id, [_offer(250, "MXP")], insights)
        assert db.latest_insights(dest.id) == insights
    finally:
        db.close()
