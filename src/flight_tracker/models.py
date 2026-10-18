"""Domain and API data models (Pydantic v2)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from flight_tracker.regions import is_region

_IATA_RE = re.compile(r"^[A-Z]{3}$")


# --------------------------------------------------------------------------- flights


class Segment(BaseModel):
    origin: str
    destination: str
    departure: datetime | None = None
    arrival: datetime | None = None
    airline: str
    flight_number: str = ""


class FlightOffer(BaseModel):
    provider: str
    destination_code: str
    price: float
    currency: str
    airlines: list[str]
    stops: int
    outbound: list[Segment]
    inbound: list[Segment] = Field(default_factory=list)
    depart_date: date
    return_date: date | None = None
    duration_minutes: int | None = None
    booking_url: str | None = None

    @property
    def connections(self) -> list[str]:
        """Intermediate airports on the outbound leg."""
        return [segment.destination for segment in self.outbound[:-1]]

    @property
    def dedupe_key(self) -> tuple[str, str, str, float]:
        flights = "|".join(f"{s.airline}{s.flight_number}" for s in self.outbound)
        return (self.destination_code, self.depart_date.isoformat(), flights, self.price)


PriceLevel = Literal["low", "typical", "high"]


class PriceInsights(BaseModel):
    """The provider's own view of the route's price (Google Flights "price insights")."""

    price_level: PriceLevel | None = None
    typical_low: float | None = None
    typical_high: float | None = None


class SearchResult(BaseModel):
    offers: list[FlightOffer] = Field(default_factory=list)
    insights: PriceInsights | None = None


class SearchQuery(BaseModel):
    origin: str
    destination: str
    depart_date: date
    return_date: date | None = None
    max_stops: int = 2
    currency: str = "USD"
    adults: int = 1


# --------------------------------------------------------------------------- destinations


def _normalize_code(value: str) -> str:
    code = value.strip().upper()
    if not (is_region(code) or _IATA_RE.match(code)):
        raise ValueError("Code must be a 3-letter IATA code or a known region key")
    return code


class Destination(BaseModel):
    id: int
    code: str
    name: str
    is_region: bool
    target_price: float | None
    max_stops: int
    trip_nights: int | None
    enabled: bool
    created_at: datetime


class DestinationCreate(BaseModel):
    code: str
    name: str | None = None
    target_price: float | None = Field(default=None, gt=0)
    max_stops: int = Field(default=1, ge=0, le=2)
    trip_nights: int | None = Field(default=7, ge=1, le=60)
    enabled: bool = True

    @field_validator("code")
    @classmethod
    def _check_code(cls, value: str) -> str:
        return _normalize_code(value)


class DestinationUpdate(BaseModel):
    name: str | None = None
    target_price: float | None = Field(default=None, gt=0)
    clear_target_price: bool = False
    max_stops: int | None = Field(default=None, ge=0, le=2)
    trip_nights: int | None = Field(default=None, ge=1, le=60)
    one_way: bool | None = None
    enabled: bool | None = None


# --------------------------------------------------------------------------- settings


class AppSettings(BaseModel):
    scheduler_enabled: bool = True
    # Conservative defaults: every (airport x date offset) pair is one paid API search.
    scan_interval_hours: float = Field(default=12.0, ge=0.25, le=72)
    date_offsets_days: list[int] = Field(default_factory=lambda: [45])
    deal_drop_percent: float = Field(default=25.0, ge=5, le=90)
    alert_cooldown_hours: float = Field(default=24.0, ge=0, le=168)
    alert_on_google_low: bool = True
    notify_desktop: bool = True
    notify_telegram: bool = False
    notify_email: bool = False

    @field_validator("date_offsets_days")
    @classmethod
    def _check_offsets(cls, value: list[int]) -> list[int]:
        cleaned = sorted({v for v in value if 1 <= v <= 330})
        if not cleaned:
            raise ValueError("At least one date offset between 1 and 330 days is required")
        if len(cleaned) > 6:
            raise ValueError("At most 6 date offsets (each one costs API calls)")
        return cleaned


# --------------------------------------------------------------------------- dashboard / alerts


class PricePoint(BaseModel):
    at: datetime
    price: float


class StoredOffer(FlightOffer):
    id: int
    destination_id: int
    destination_name: str
    found_at: datetime


class DashboardRow(BaseModel):
    destination: Destination
    current_price: float | None
    lowest_price: float | None
    lowest_seen_at: datetime | None
    average_price: float | None
    change_percent: float | None
    trend: Literal["up", "down", "flat", "unknown"]
    history: list[PricePoint]
    last_checked: datetime | None
    best_offer: StoredOffer | None
    below_target: bool
    insights: PriceInsights | None


AlertKind = Literal["target", "deal", "google_low"]


class AlertRecord(BaseModel):
    id: int
    created_at: datetime
    destination_id: int
    destination_name: str
    kind: AlertKind
    price: float
    currency: str
    message: str


class ScanStatus(BaseModel):
    running: bool = False
    provider: str = ""
    last_started: datetime | None = None
    last_finished: datetime | None = None
    next_run: datetime | None = None
    progress: str = ""
    errors: list[str] = Field(default_factory=list)
