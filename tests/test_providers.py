from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from typing import Any

import httpx
import pytest
import respx

from flight_tracker.config import Config, ProviderName
from flight_tracker.models import SearchQuery
from flight_tracker.providers import (
    ProviderAuthError,
    ProviderConfigError,
    ProviderUnavailableError,
    provider_key,
)
from flight_tracker.providers.base import FlightProvider
from flight_tracker.providers.mock import MockProvider
from flight_tracker.providers.serpapi import SerpApiProvider

SERPAPI_URL = "https://serpapi.com/search.json"
QUERY = SearchQuery(origin="TLV", destination="LHR", depart_date=date(2026, 12, 1), max_stops=1)


def _flight(src: str, dst: str, dep: str, arr: str, number: str) -> dict[str, Any]:
    return {
        "departure_airport": {"id": src, "time": dep},
        "arrival_airport": {"id": dst, "time": arr},
        "airline": "Turkish Airlines",
        "flight_number": number,
    }


SERPAPI_PAYLOAD: dict[str, Any] = {
    "search_metadata": {"google_flights_url": "https://www.google.com/travel/flights?x"},
    "best_flights": [
        {
            "price": 412,
            "total_duration": 420,
            "flights": [
                _flight("TLV", "IST", "2026-12-01 06:00", "2026-12-01 08:10", "TK 785"),
                _flight("IST", "LHR", "2026-12-01 10:00", "2026-12-01 12:00", "TK 1971"),
            ],
        }
    ],
    "other_flights": [{"price": 380, "flights": [{"airline": "A"}, {"airline": "B"}, {"airline": "C"}]}],
}


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(attempt: int, explicit_delay: float | None = None) -> None:
        return None

    monkeypatch.setattr(FlightProvider, "_backoff", staticmethod(instant))


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as http:
        yield http


@respx.mock
async def test_serpapi_parses_connections_and_filters_stops(client: httpx.AsyncClient) -> None:
    respx.get(SERPAPI_URL).respond(json=SERPAPI_PAYLOAD)
    offers = await SerpApiProvider(client, "key").search(QUERY)

    assert len(offers) == 1  # the 2-stop offer is filtered out (max_stops=1)
    offer = offers[0]
    assert offer.price == 412
    assert offer.connections == ["IST"]
    assert offer.outbound[0].flight_number == "TK785"


@respx.mock
async def test_auth_error_is_not_retried(client: httpx.AsyncClient) -> None:
    route = respx.get(SERPAPI_URL).respond(401)
    with pytest.raises(ProviderAuthError):
        await SerpApiProvider(client, "bad").search(QUERY)
    assert route.call_count == 1


@respx.mock
async def test_server_errors_are_retried_then_raise(client: httpx.AsyncClient) -> None:
    route = respx.get(SERPAPI_URL).respond(503)
    with pytest.raises(ProviderUnavailableError):
        await SerpApiProvider(client, "key").search(QUERY)
    assert route.call_count == SerpApiProvider.max_retries


@respx.mock
async def test_network_error_recovers(client: httpx.AsyncClient) -> None:
    respx.get(SERPAPI_URL).mock(
        side_effect=[httpx.ConnectError("boom"), httpx.Response(200, json=SERPAPI_PAYLOAD)]
    )
    assert await SerpApiProvider(client, "key").search(QUERY)


def test_missing_key_is_a_config_error(config: Config) -> None:
    serpapi_config = config.model_copy(update={"flight_provider": ProviderName.SERPAPI})
    with pytest.raises(ProviderConfigError, match="SERPAPI_API_KEY"):
        provider_key(serpapi_config)
    assert provider_key(config) == ""  # mock needs no key


async def test_mock_provider_is_deterministic(client: httpx.AsyncClient) -> None:
    provider = MockProvider(client)
    first, second = await provider.search(QUERY), await provider.search(QUERY)
    assert [o.price for o in first] == [o.price for o in second]
    assert all(o.stops <= QUERY.max_stops for o in first)
