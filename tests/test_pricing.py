from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from flight_tracker.models import AppSettings, PriceInsights, PricePoint
from flight_tracker.services.pricing import (
    PriceContext,
    describe_stops,
    evaluate_price,
    is_repeat_alert,
    price_trend,
)

SETTINGS = AppSettings(deal_drop_percent=25, alert_on_google_low=True)
GOOGLE_LOW = PriceInsights(price_level="low", typical_low=430, typical_high=670)


def _history(*prices: float) -> list[PricePoint]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [PricePoint(at=start + timedelta(hours=i), price=p) for i, p in enumerate(prices)]


def test_target_price_hit() -> None:
    decision = evaluate_price(199, PriceContext(target_price=200), SETTINGS)
    assert decision is not None
    assert decision.kind == "target"


def test_deal_requires_enough_history() -> None:
    assert evaluate_price(100, PriceContext(average_price=300, sample_size=2), SETTINGS) is None
    decision = evaluate_price(100, PriceContext(average_price=300, sample_size=3), SETTINGS)
    assert decision is not None
    assert decision.kind == "deal"


def test_no_alert_for_normal_price() -> None:
    context = PriceContext(target_price=200, average_price=300, sample_size=10)
    assert evaluate_price(290, context, SETTINGS) is None


def test_google_low_alerts_without_any_history() -> None:
    decision = evaluate_price(400, PriceContext(insights=GOOGLE_LOW), SETTINGS)
    assert decision is not None
    assert decision.kind == "google_low"
    assert "430–670" in decision.reason


@pytest.mark.parametrize("level", ["typical", "high", None])
def test_google_other_levels_do_not_alert(level: str | None) -> None:
    insights = PriceInsights.model_validate({"price_level": level, "typical_low": 430, "typical_high": 670})
    assert evaluate_price(500, PriceContext(insights=insights), SETTINGS) is None


def test_google_low_can_be_disabled() -> None:
    settings = SETTINGS.model_copy(update={"alert_on_google_low": False})
    assert evaluate_price(400, PriceContext(insights=GOOGLE_LOW), settings) is None


def test_target_rule_wins_over_google_low() -> None:
    decision = evaluate_price(400, PriceContext(target_price=450, insights=GOOGLE_LOW), SETTINGS)
    assert decision is not None
    assert decision.kind == "target"


@pytest.mark.parametrize(
    ("price", "last", "expected"),
    [(100, None, False), (100, 100, True), (120, 100, True), (90, 100, False)],
)
def test_repeat_alert(price: float, last: float | None, expected: bool) -> None:
    assert is_repeat_alert(price, last) is expected


@pytest.mark.parametrize(
    ("stops", "connections", "expected"),
    [
        (0, [], "טיסה ישירה"),
        (1, ["IST"], "עצירה אחת דרך IST"),
        (2, ["IST", "VIE"], "2 עצירות דרך IST, VIE"),
        (1, [], "עצירה אחת"),
    ],
)
def test_describe_stops(stops: int, connections: list[str], expected: str) -> None:
    assert describe_stops(stops, connections) == expected


def test_trend_directions() -> None:
    assert price_trend(_history(100))[0] == "unknown"
    assert price_trend(_history(100, 90))[0] == "down"
    assert price_trend(_history(100, 110))[0] == "up"
    assert price_trend(_history(100, 101))[0] == "flat"
