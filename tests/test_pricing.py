from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from flight_tracker.models import PricePoint
from flight_tracker.services.pricing import evaluate_price, is_repeat_alert, price_trend


def _history(*prices: float) -> list[PricePoint]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [PricePoint(at=start + timedelta(hours=i), price=p) for i, p in enumerate(prices)]


def test_target_price_hit() -> None:
    decision = evaluate_price(199, target_price=200, average_price=None, sample_size=0, deal_drop_percent=25)
    assert decision is not None
    assert decision.kind == "target"


def test_deal_requires_enough_history() -> None:
    assert (
        evaluate_price(100, target_price=None, average_price=300, sample_size=2, deal_drop_percent=25) is None
    )
    decision = evaluate_price(100, target_price=None, average_price=300, sample_size=3, deal_drop_percent=25)
    assert decision is not None
    assert decision.kind == "deal"


def test_no_alert_for_normal_price() -> None:
    assert (
        evaluate_price(290, target_price=200, average_price=300, sample_size=10, deal_drop_percent=25) is None
    )


@pytest.mark.parametrize(
    ("price", "last", "expected"),
    [(100, None, False), (100, 100, True), (120, 100, True), (90, 100, False)],
)
def test_repeat_alert(price: float, last: float | None, expected: bool) -> None:
    assert is_repeat_alert(price, last) is expected


def test_trend_directions() -> None:
    assert price_trend(_history(100))[0] == "unknown"
    assert price_trend(_history(100, 90))[0] == "down"
    assert price_trend(_history(100, 110))[0] == "up"
    assert price_trend(_history(100, 101))[0] == "flat"
