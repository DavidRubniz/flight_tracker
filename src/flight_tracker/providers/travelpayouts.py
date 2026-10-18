"""Aviasales cached prices via the Travelpayouts Data API (free).

Prices come from recent user searches (cache), not a live query - great for
spotting deals cheaply, but always confirm on the booking site.
Docs: https://support.travelpayouts.com/hc/en-us/articles/203956163
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from flight_tracker.models import FlightOffer, SearchQuery, SearchResult, Segment
from flight_tracker.providers.base import FlightProvider, ProviderError

_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


def _parse_dt(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


class TravelpayoutsProvider(FlightProvider):
    name = "travelpayouts"

    def __init__(self, client: httpx.AsyncClient, token: str) -> None:
        super().__init__(client)
        self._token = token

    async def search(self, query: SearchQuery) -> SearchResult:
        params: dict[str, str | int] = {
            "origin": query.origin,
            "destination": query.destination,
            "departure_at": query.depart_date.strftime("%Y-%m"),
            "one_way": "false" if query.return_date else "true",
            "direct": "true" if query.max_stops == 0 else "false",
            "currency": query.currency.lower(),
            "sorting": "price",
            "limit": 10,
            "token": self._token,
        }
        if query.return_date:
            params["return_at"] = query.return_date.strftime("%Y-%m")

        payload = await self._request_json("GET", _URL, params=params)
        if payload.get("success") is False:
            raise ProviderError(f"travelpayouts: {payload.get('error', 'request failed')}")
        offers = [o for raw in (payload.get("data") or []) if (o := self._parse(raw, query))]
        return SearchResult(offers=[o for o in offers if o.stops <= query.max_stops])

    def _parse(self, raw: dict[str, Any], query: SearchQuery) -> FlightOffer | None:
        price = raw.get("price")
        departure = _parse_dt(raw.get("departure_at"))
        if not isinstance(price, (int, float)) or departure is None:
            return None
        returning = _parse_dt(raw.get("return_at"))
        airline = str(raw.get("airline", ""))
        # The cached API exposes the number of transfers but not the transfer airports.
        segment = Segment(
            origin=str(raw.get("origin_airport") or query.origin),
            destination=str(raw.get("destination_airport") or query.destination),
            departure=departure,
            arrival=None,
            airline=airline,
            flight_number=f"{airline}{raw.get('flight_number', '')}",
        )
        link = raw.get("link")
        return FlightOffer(
            provider=self.name,
            destination_code=query.destination,
            price=float(price),
            currency=query.currency,
            airlines=[airline] if airline else [],
            stops=int(raw.get("transfers") or 0),
            outbound=[segment],
            depart_date=departure.date(),
            return_date=returning.date() if returning else None,
            duration_minutes=raw.get("duration_to") or raw.get("duration"),
            booking_url=f"https://www.aviasales.com{link}" if isinstance(link, str) else None,
        )
