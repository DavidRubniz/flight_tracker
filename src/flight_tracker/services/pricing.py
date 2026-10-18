"""Pure price-analysis rules (no I/O) - the place to tweak *when* an alert fires."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from flight_tracker.models import AlertKind, PricePoint

Trend = Literal["up", "down", "flat", "unknown"]

MIN_SAMPLES_FOR_DEAL = 3
FLAT_THRESHOLD_PERCENT = 2.0


@dataclass(frozen=True, slots=True)
class AlertDecision:
    kind: AlertKind
    reason: str


def evaluate_price(
    price: float,
    *,
    target_price: float | None,
    average_price: float | None,
    sample_size: int,
    deal_drop_percent: float,
) -> AlertDecision | None:
    """Decide whether ``price`` deserves an alert.

    * ``target`` - price is at or below the user's ceiling for this destination.
    * ``deal``   - price is ``deal_drop_percent``% below the recent average
      (only once there is enough history to trust the average).
    """
    if target_price is not None and price <= target_price:
        return AlertDecision("target", f"המחיר ירד מתחת ליעד שהגדרת ({target_price:,.0f})")
    if average_price and sample_size >= MIN_SAMPLES_FOR_DEAL:
        drop = (1 - price / average_price) * 100
        if drop >= deal_drop_percent:
            return AlertDecision("deal", f"מציאה! זול ב-{drop:.0f}% מהממוצע ({average_price:,.0f})")
    return None


def is_repeat_alert(price: float, last_alert_price: float | None) -> bool:
    """An alert is a repeat if we already alerted at the same or a lower price recently."""
    return last_alert_price is not None and price >= last_alert_price


def describe_stops(stops: int, connections: Sequence[str]) -> str:
    """Hebrew description of the connections, e.g. 'עצירה אחת דרך IST'."""
    if stops == 0:
        return "טיסה ישירה"
    label = "עצירה אחת" if stops == 1 else f"{stops} עצירות"
    # Some providers (e.g. Travelpayouts) report the number of stops but not the airports.
    return f"{label} דרך {', '.join(connections)}" if connections else label


def price_trend(history: Sequence[PricePoint]) -> tuple[Trend, float | None]:
    """Compare the latest price with the previous one. Returns (direction, change %)."""
    if len(history) < 2:
        return "unknown", None
    previous, latest = history[-2].price, history[-1].price
    if previous <= 0:
        return "unknown", None
    change = (latest - previous) / previous * 100
    if abs(change) < FLAT_THRESHOLD_PERCENT:
        return "flat", change
    return ("up" if change > 0 else "down"), change
