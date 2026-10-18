"""Live airline offers via the Duffel API (https://duffel.com/docs/api/offer-requests)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from flight_tracker.models import FlightOffer, SearchQuery, SearchResult, Segment
from flight_tracker.providers.base import FlightProvider, ProviderError

_URL = "https://api.duffel.com/air/offer_requests"
_MAX_OFFERS = 12


def _parse_dt(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


class DuffelProvider(FlightProvider):
    name = "duffel"

    def __init__(self, client: httpx.AsyncClient, token: str) -> None:
        super().__init__(client)
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Duffel-Version": "v2",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def search(self, query: SearchQuery) -> SearchResult:
        slices: list[dict[str, str]] = [
            {
                "origin": query.origin,
                "destination": query.destination,
                "departure_date": query.depart_date.isoformat(),
            }
        ]
        if query.return_date:
            slices.append(
                {
                    "origin": query.destination,
                    "destination": query.origin,
                    "departure_date": query.return_date.isoformat(),
                }
            )
        body: dict[str, Any] = {
            "data": {
                "slices": slices,
                "passengers": [{"type": "adult"} for _ in range(query.adults)],
                "cabin_class": "economy",
                "max_connections": query.max_stops,
            }
        }
        payload = await self._request_json(
            "POST",
            _URL,
            params={"return_offers": "true", "supplier_timeout": 20000},
            json_body=body,
            headers=self._headers,
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ProviderError("duffel: response has no 'data' object")
        offers = [o for raw in (data.get("offers") or []) if (o := self._parse(raw, query))]
        offers.sort(key=lambda o: o.price)
        return SearchResult(offers=offers[:_MAX_OFFERS])

    @staticmethod
    def _segments(slice_obj: dict[str, Any]) -> list[Segment]:
        result: list[Segment] = []
        for seg in slice_obj.get("segments") or []:
            carrier = seg.get("marketing_carrier") or {}
            number = f"{carrier.get('iata_code', '')}{seg.get('marketing_carrier_flight_number', '')}"
            result.append(
                Segment(
                    origin=str((seg.get("origin") or {}).get("iata_code", "")),
                    destination=str((seg.get("destination") or {}).get("iata_code", "")),
                    departure=_parse_dt(seg.get("departing_at")),
                    arrival=_parse_dt(seg.get("arriving_at")),
                    airline=str(carrier.get("name", "")),
                    flight_number=number,
                )
            )
        return result

    def _parse(self, raw: dict[str, Any], query: SearchQuery) -> FlightOffer | None:
        try:
            price = float(raw["total_amount"])
        except (KeyError, TypeError, ValueError):
            return None
        slices = raw.get("slices") or []
        if not slices:
            return None
        outbound = self._segments(slices[0])
        inbound = self._segments(slices[1]) if len(slices) > 1 else []
        if not outbound:
            return None
        duration: int | None = None
        if outbound[0].departure and outbound[-1].arrival:
            duration = int((outbound[-1].arrival - outbound[0].departure).total_seconds() // 60)
        return FlightOffer(
            provider=self.name,
            destination_code=query.destination,
            price=price,
            currency=str(raw.get("total_currency", query.currency)),
            airlines=sorted({s.airline for s in outbound + inbound if s.airline}),
            stops=len(outbound) - 1,
            outbound=outbound,
            inbound=inbound,
            depart_date=query.depart_date,
            return_date=query.return_date,
            duration_minutes=duration,
            booking_url=None,
        )
