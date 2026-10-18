"""Google Flights results via SerpApi (https://serpapi.com/google-flights-api).

Recommended source: real-time Google Flights prices incl. connections and airlines.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from flight_tracker.models import FlightOffer, SearchQuery, Segment
from flight_tracker.providers.base import FlightProvider, ProviderError

_URL = "https://serpapi.com/search.json"
# SerpApi "stops": 1 = nonstop only, 2 = up to 1 stop, 3 = up to 2 stops
_STOPS_PARAM: dict[int, int] = {0: 1, 1: 2, 2: 3}


def _parse_time(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError:
        return None


class SerpApiProvider(FlightProvider):
    name = "serpapi"

    def __init__(self, client: httpx.AsyncClient, api_key: str) -> None:
        super().__init__(client)
        self._api_key = api_key

    async def search(self, query: SearchQuery) -> list[FlightOffer]:
        params: dict[str, str | int] = {
            "engine": "google_flights",
            "departure_id": query.origin,
            "arrival_id": query.destination,
            "outbound_date": query.depart_date.isoformat(),
            "type": 1 if query.return_date else 2,
            "currency": query.currency,
            "hl": "en",
            "gl": "il",
            "adults": query.adults,
            "stops": _STOPS_PARAM.get(query.max_stops, 0),
            "api_key": self._api_key,
        }
        if query.return_date:
            params["return_date"] = query.return_date.isoformat()

        payload = await self._request_json("GET", _URL, params=params)
        if error := payload.get("error"):
            if "hasn't returned any results" in str(error):
                return []
            raise ProviderError(f"serpapi: {error}")

        booking_url = (payload.get("search_metadata") or {}).get("google_flights_url")
        raw_items: list[Any] = [*(payload.get("best_flights") or []), *(payload.get("other_flights") or [])]
        offers = [o for item in raw_items if (o := self._parse(item, query, booking_url))]
        return [o for o in offers if o.stops <= query.max_stops]

    def _parse(self, item: dict[str, Any], query: SearchQuery, booking_url: str | None) -> FlightOffer | None:
        price = item.get("price")
        flights = item.get("flights") or []
        if not isinstance(price, (int, float)) or not flights:
            return None
        segments = [
            Segment(
                origin=str((f.get("departure_airport") or {}).get("id", "")),
                destination=str((f.get("arrival_airport") or {}).get("id", "")),
                departure=_parse_time((f.get("departure_airport") or {}).get("time")),
                arrival=_parse_time((f.get("arrival_airport") or {}).get("time")),
                airline=str(f.get("airline", "")),
                flight_number=str(f.get("flight_number", "")).replace(" ", ""),
            )
            for f in flights
        ]
        return FlightOffer(
            provider=self.name,
            destination_code=query.destination,
            price=float(price),
            currency=query.currency,
            airlines=sorted({s.airline for s in segments if s.airline}),
            stops=len(segments) - 1,
            outbound=segments,
            depart_date=query.depart_date,
            return_date=query.return_date,
            duration_minutes=item.get("total_duration"),
            booking_url=booking_url,
        )
