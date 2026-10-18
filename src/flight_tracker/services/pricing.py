"""Pure price-analysis rules (no I/O) - the place to tweak *when* an alert fires."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from flight_tracker.models import AlertKind, AppSettings, PriceInsights, PricePoint

Trend = Literal["up", "down", "flat", "unknown"]

MIN_SAMPLES_FOR_DEAL = 3
FLAT_THRESHOLD_PERCENT = 2.0


@dataclass(frozen=True, slots=True)
class AlertDecision:
    kind: AlertKind
    reason: str


@dataclass(frozen=True, slots=True)
class PriceContext:
    """Everything known about a destination's price apart from the current offer."""

    target_price: float | None = None
    average_price: float | None = None
    sample_size: int = 0
    insights: PriceInsights | None = None


def evaluate_price(price: float, context: PriceContext, settings: AppSettings) -> AlertDecision | None:
    """Decide whether ``price`` deserves an alert. Rules, in priority order:

    * ``target``     - price is at or below the user's ceiling for this destination.
    * ``deal``       - price is ``deal_drop_percent``% below our own recent average
      (only once there is enough history to trust the average).
    * ``google_low`` - Google Flights rates the price as low for this route. Works from
      the very first scan, since it relies on Google's history rather than ours.
    """
    target, average, insights = context.target_price, context.average_price, context.insights
    if target is not None and price <= target:
        return AlertDecision("target", f"המחיר ירד מתחת ליעד שהגדרת ({target:,.0f})")
    if average and context.sample_size >= MIN_SAMPLES_FOR_DEAL:
        drop = (1 - price / average) * 100
        if drop >= settings.deal_drop_percent:
            return AlertDecision("deal", f"מציאה! זול ב-{drop:.0f}% מהממוצע ({average:,.0f})")
    if settings.alert_on_google_low and insights and insights.price_level == "low":
        typical = (
            f" (טווח רגיל: {insights.typical_low:,.0f}–{insights.typical_high:,.0f})"
            if insights.typical_low is not None and insights.typical_high is not None
            else ""
        )
        return AlertDecision("google_low", f"Google מסמנת את המחיר כנמוך מהרגיל{typical}")
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
