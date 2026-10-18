"""SQLite persistence layer (thread-safe, single connection)."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from flight_tracker.models import (
    AlertKind,
    AlertRecord,
    AppSettings,
    Destination,
    DestinationCreate,
    DestinationUpdate,
    FlightOffer,
    PriceInsights,
    PricePoint,
    Segment,
    StoredOffer,
)
from flight_tracker.regions import display_name, is_region

_SCHEMA = """
CREATE TABLE IF NOT EXISTS destinations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    is_region     INTEGER NOT NULL DEFAULT 0,
    target_price  REAL,
    max_stops     INTEGER NOT NULL DEFAULT 1,
    trip_nights   INTEGER,
    enabled       INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    destination_id INTEGER NOT NULL REFERENCES destinations(id) ON DELETE CASCADE,
    checked_at     TEXT NOT NULL,
    min_price      REAL NOT NULL,
    currency       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_snapshots_dest ON snapshots(destination_id, checked_at);
CREATE TABLE IF NOT EXISTS offers (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id      INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    destination_id   INTEGER NOT NULL REFERENCES destinations(id) ON DELETE CASCADE,
    provider         TEXT NOT NULL,
    destination_code TEXT NOT NULL,
    price            REAL NOT NULL,
    currency         TEXT NOT NULL,
    airlines         TEXT NOT NULL,
    stops            INTEGER NOT NULL,
    outbound         TEXT NOT NULL,
    inbound          TEXT NOT NULL,
    depart_date      TEXT NOT NULL,
    return_date      TEXT,
    duration_minutes INTEGER,
    booking_url      TEXT
);
CREATE INDEX IF NOT EXISTS ix_offers_snapshot ON offers(snapshot_id);
CREATE TABLE IF NOT EXISTS alerts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT NOT NULL,
    destination_id INTEGER NOT NULL REFERENCES destinations(id) ON DELETE CASCADE,
    kind           TEXT NOT NULL,
    price          REAL NOT NULL,
    currency       TEXT NOT NULL,
    message        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Lightweight schema migrations: (table, column, type) added after the table's first
# release. Applied on every start when missing, so existing databases keep their data.
# Append new columns here instead of editing _SCHEMA.
_ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("snapshots", "price_level", "TEXT"),
    ("snapshots", "typical_low", "REAL"),
    ("snapshots", "typical_high", "REAL"),
)

_DEFAULT_DESTINATIONS: tuple[DestinationCreate, ...] = (
    DestinationCreate(code="ATH", target_price=180, max_stops=0, trip_nights=5),
    DestinationCreate(code="LHR", target_price=350, max_stops=1, trip_nights=7),
    DestinationCreate(code="BKK", target_price=650, max_stops=1, trip_nights=14),
    DestinationCreate(code="JFK", target_price=750, max_stops=1, trip_nights=10),
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _to_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _segments_to_json(segments: Sequence[Segment]) -> str:
    return json.dumps([s.model_dump(mode="json") for s in segments], ensure_ascii=False)


def _segments_from_json(raw: str) -> list[Segment]:
    return [Segment.model_validate(item) for item in json.loads(raw)]


class Database:
    def __init__(self, path: Path) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._lock = threading.RLock()
        with self._tx() as cur:
            cur.executescript(_SCHEMA)
            self._migrate(cur)
        if not self.list_destinations():
            for item in _DEFAULT_DESTINATIONS:
                self.add_destination(item)

    @staticmethod
    def _migrate(cur: sqlite3.Cursor) -> None:
        """Add columns introduced after a table was first created (idempotent)."""
        for table, column, sql_type in _ADDED_COLUMNS:
            existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Cursor]:
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            finally:
                cur.close()

    def _query(self, sql: str, params: Sequence[Any] | Mapping[str, Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ destinations

    @staticmethod
    def _row_to_destination(row: sqlite3.Row) -> Destination:
        return Destination(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            is_region=bool(row["is_region"]),
            target_price=row["target_price"],
            max_stops=row["max_stops"],
            trip_nights=row["trip_nights"],
            enabled=bool(row["enabled"]),
            created_at=_to_dt(row["created_at"]),
        )

    def list_destinations(self, only_enabled: bool = False) -> list[Destination]:
        sql = "SELECT * FROM destinations"
        if only_enabled:
            sql += " WHERE enabled = 1"
        return [self._row_to_destination(r) for r in self._query(sql + " ORDER BY id")]

    def get_destination(self, destination_id: int) -> Destination | None:
        rows = self._query("SELECT * FROM destinations WHERE id = ?", (destination_id,))
        return self._row_to_destination(rows[0]) if rows else None

    def add_destination(self, data: DestinationCreate) -> Destination:
        with self._tx() as cur:
            cur.execute(
                """INSERT INTO destinations
                   (code, name, is_region, target_price, max_stops, trip_nights, enabled, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data.code,
                    data.name or display_name(data.code),
                    int(is_region(data.code)),
                    data.target_price,
                    data.max_stops,
                    data.trip_nights,
                    int(data.enabled),
                    utcnow().isoformat(),
                ),
            )
            new_id = cur.lastrowid
        created = self.get_destination(int(new_id or 0))
        if created is None:
            raise RuntimeError("Failed to create destination")
        return created

    def update_destination(self, destination_id: int, data: DestinationUpdate) -> Destination | None:
        current = self.get_destination(destination_id)
        if current is None:
            return None
        target = None if data.clear_target_price else (data.target_price or current.target_price)
        nights = None if data.one_way else (data.trip_nights or current.trip_nights)
        if data.one_way is False and nights is None:
            nights = 7
        with self._tx() as cur:
            cur.execute(
                """UPDATE destinations SET name = ?, target_price = ?, max_stops = ?,
                   trip_nights = ?, enabled = ? WHERE id = ?""",
                (
                    data.name or current.name,
                    target,
                    current.max_stops if data.max_stops is None else data.max_stops,
                    nights,
                    int(current.enabled if data.enabled is None else data.enabled),
                    destination_id,
                ),
            )
        return self.get_destination(destination_id)

    def delete_destination(self, destination_id: int) -> bool:
        with self._tx() as cur:
            cur.execute("DELETE FROM destinations WHERE id = ?", (destination_id,))
            return cur.rowcount > 0

    # ------------------------------------------------------------------ settings

    def get_settings(self) -> AppSettings:
        rows = self._query("SELECT value FROM settings WHERE key = 'app'")
        if not rows:
            return AppSettings()
        try:
            return AppSettings.model_validate_json(rows[0]["value"])
        except ValueError:
            return AppSettings()

    def save_settings(self, settings: AppSettings) -> AppSettings:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO settings (key, value) VALUES ('app', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (settings.model_dump_json(),),
            )
        return settings

    # ------------------------------------------------------------------ prices & offers

    def record_scan(
        self,
        destination_id: int,
        offers: Sequence[FlightOffer],
        insights: PriceInsights | None = None,
    ) -> int:
        """Store a scan result. ``offers`` must be non-empty and sorted by price."""
        if not offers:
            raise ValueError("record_scan requires at least one offer")
        now = utcnow().isoformat()
        with self._tx() as cur:
            cur.execute(
                """INSERT INTO snapshots (destination_id, checked_at, min_price, currency,
                   price_level, typical_low, typical_high) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    destination_id,
                    now,
                    offers[0].price,
                    offers[0].currency,
                    insights.price_level if insights else None,
                    insights.typical_low if insights else None,
                    insights.typical_high if insights else None,
                ),
            )
            snapshot_id = int(cur.lastrowid or 0)
            cur.executemany(
                """INSERT INTO offers (snapshot_id, destination_id, provider, destination_code, price,
                   currency, airlines, stops, outbound, inbound, depart_date, return_date,
                   duration_minutes, booking_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        snapshot_id,
                        destination_id,
                        o.provider,
                        o.destination_code,
                        o.price,
                        o.currency,
                        json.dumps(o.airlines, ensure_ascii=False),
                        o.stops,
                        _segments_to_json(o.outbound),
                        _segments_to_json(o.inbound),
                        o.depart_date.isoformat(),
                        o.return_date.isoformat() if o.return_date else None,
                        o.duration_minutes,
                        o.booking_url,
                    )
                    for o in offers
                ],
            )
            # Keep the full offer details only for the last 30 days (snapshots stay forever).
            cutoff = (utcnow() - timedelta(days=30)).isoformat()
            cur.execute(
                "DELETE FROM offers WHERE snapshot_id IN (SELECT id FROM snapshots WHERE checked_at < ?)",
                (cutoff,),
            )
        return snapshot_id

    def price_history(self, destination_id: int, days: int = 30) -> list[PricePoint]:
        since = (utcnow() - timedelta(days=days)).isoformat()
        rows = self._query(
            "SELECT checked_at, min_price FROM snapshots WHERE destination_id = ? AND checked_at >= ? "
            "ORDER BY checked_at",
            (destination_id, since),
        )
        return [PricePoint(at=_to_dt(r["checked_at"]), price=r["min_price"]) for r in rows]

    def last_scan_at(self) -> datetime | None:
        rows = self._query("SELECT MAX(checked_at) AS last FROM snapshots")
        return _to_dt(rows[0]["last"]) if rows and rows[0]["last"] else None

    def latest_insights(self, destination_id: int) -> PriceInsights | None:
        rows = self._query(
            "SELECT price_level, typical_low, typical_high FROM snapshots "
            "WHERE destination_id = ? ORDER BY id DESC LIMIT 1",
            (destination_id,),
        )
        if not rows or all(rows[0][key] is None for key in ("price_level", "typical_low", "typical_high")):
            return None
        return PriceInsights(
            price_level=rows[0]["price_level"],
            typical_low=rows[0]["typical_low"],
            typical_high=rows[0]["typical_high"],
        )

    def lowest_price(self, destination_id: int) -> tuple[float, datetime] | None:
        rows = self._query(
            "SELECT min_price, checked_at FROM snapshots WHERE destination_id = ? "
            "ORDER BY min_price ASC, checked_at DESC LIMIT 1",
            (destination_id,),
        )
        return (rows[0]["min_price"], _to_dt(rows[0]["checked_at"])) if rows else None

    def average_price(self, destination_id: int, days: int = 30) -> tuple[float | None, int]:
        since = (utcnow() - timedelta(days=days)).isoformat()
        rows = self._query(
            "SELECT AVG(min_price) AS avg, COUNT(*) AS n FROM snapshots "
            "WHERE destination_id = ? AND checked_at >= ?",
            (destination_id, since),
        )
        return (rows[0]["avg"], int(rows[0]["n"])) if rows else (None, 0)

    def _row_to_offer(self, row: sqlite3.Row) -> StoredOffer:
        return StoredOffer(
            id=row["id"],
            destination_id=row["destination_id"],
            destination_name=row["dest_name"],
            found_at=_to_dt(row["checked_at"]),
            provider=row["provider"],
            destination_code=row["destination_code"],
            price=row["price"],
            currency=row["currency"],
            airlines=json.loads(row["airlines"]),
            stops=row["stops"],
            outbound=_segments_from_json(row["outbound"]),
            inbound=_segments_from_json(row["inbound"]),
            depart_date=date.fromisoformat(row["depart_date"]),
            return_date=date.fromisoformat(row["return_date"]) if row["return_date"] else None,
            duration_minutes=row["duration_minutes"],
            booking_url=row["booking_url"],
        )

    def latest_offers(self, destination_id: int | None = None, limit: int = 60) -> list[StoredOffer]:
        """Offers from the most recent snapshot of each (or one) destination, cheapest first."""
        rows = self._query(
            """SELECT o.*, s.checked_at, d.name AS dest_name
               FROM offers o
               JOIN snapshots s ON s.id = o.snapshot_id
               JOIN destinations d ON d.id = o.destination_id
               WHERE s.id IN (SELECT MAX(id) FROM snapshots GROUP BY destination_id)
                 AND (:dest IS NULL OR o.destination_id = :dest)
               ORDER BY o.price ASC LIMIT :limit""",
            {"dest": destination_id, "limit": limit},
        )
        return [self._row_to_offer(r) for r in rows]

    # ------------------------------------------------------------------ alerts

    def add_alert(
        self, destination_id: int, kind: AlertKind, price: float, currency: str, message: str
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO alerts (created_at, destination_id, kind, price, currency, message) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (utcnow().isoformat(), destination_id, kind, price, currency, message),
            )

    def last_alert_price(self, destination_id: int, within_hours: float) -> float | None:
        since = (utcnow() - timedelta(hours=within_hours)).isoformat()
        rows = self._query(
            "SELECT MIN(price) AS p FROM alerts WHERE destination_id = ? AND created_at >= ?",
            (destination_id, since),
        )
        return rows[0]["p"] if rows and rows[0]["p"] is not None else None

    def list_alerts(self, limit: int = 100) -> list[AlertRecord]:
        rows = self._query(
            """SELECT a.*, d.name AS dest_name FROM alerts a
               JOIN destinations d ON d.id = a.destination_id
               ORDER BY a.created_at DESC LIMIT ?""",
            (limit,),
        )
        return [
            AlertRecord(
                id=r["id"],
                created_at=_to_dt(r["created_at"]),
                destination_id=r["destination_id"],
                destination_name=r["dest_name"],
                kind=r["kind"],
                price=r["price"],
                currency=r["currency"],
                message=r["message"],
            )
            for r in rows
        ]
