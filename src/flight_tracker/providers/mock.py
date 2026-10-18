"""Offline demo provider producing realistic-looking, slowly drifting prices.

Lets you try the whole app (dashboard, trends, alerts) without any API key.
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import random
from datetime import date, datetime, time, timedelta

from flight_tracker.models import FlightOffer, SearchQuery, Segment
from flight_tracker.providers.base import FlightProvider

_BASE_PRICE: dict[str, float] = {
    "ATH": 190,
    "LCA": 140,
    "PFO": 150,
    "SKG": 210,
    "HER": 230,
    "RHO": 210,
    "BUD": 230,
    "PRG": 260,
    "VIE": 280,
    "BER": 290,
    "FCO": 290,
    "BCN": 330,
    "AMS": 340,
    "CDG": 350,
    "LHR": 380,
    "OTP": 200,
    "SOF": 210,
    "WAW": 240,
    "KRK": 230,
    "TBS": 260,
    "BEG": 240,
    "JFK": 820,
    "EWR": 790,
    "BOS": 860,
    "MIA": 900,
    "LAX": 980,
    "SFO": 1010,
    "BKK": 690,
    "HKT": 740,
    "DEL": 560,
    "BOM": 590,
    "NRT": 980,
    "SIN": 820,
    "DXB": 300,
}
_DIRECT_FROM_TLV: set[str] = {
    "ATH",
    "LCA",
    "PFO",
    "SKG",
    "HER",
    "RHO",
    "BUD",
    "PRG",
    "VIE",
    "BER",
    "FCO",
    "BCN",
    "AMS",
    "CDG",
    "LHR",
    "OTP",
    "SOF",
    "WAW",
    "KRK",
    "TBS",
    "BEG",
    "JFK",
    "EWR",
    "BOS",
    "MIA",
    "LAX",
    "SFO",
    "BKK",
    "DEL",
    "BOM",
    "NRT",
    "DXB",
}
_DIRECT_AIRLINES: tuple[tuple[str, str], ...] = (
    ("LY", "El Al"),
    ("IZ", "Arkia"),
    ("6H", "Israir"),
    ("W6", "Wizz Air"),
    ("FR", "Ryanair"),
)
_HUBS: tuple[tuple[str, str, str], ...] = (
    ("IST", "TK", "Turkish Airlines"),
    ("ATH", "A3", "Aegean Airlines"),
    ("VIE", "OS", "Austrian"),
    ("FRA", "LH", "Lufthansa"),
    ("MUC", "LH", "Lufthansa"),
    ("ZRH", "LX", "Swiss"),
    ("WAW", "LO", "LOT Polish"),
    ("DXB", "FZ", "flydubai"),
    ("AUH", "EY", "Etihad"),
    ("LHR", "BA", "British Airways"),
    ("CDG", "AF", "Air France"),
)


class MockProvider(FlightProvider):
    name = "mock"
    max_retries = 1

    async def search(self, query: SearchQuery) -> list[FlightOffer]:
        await asyncio.sleep(0.05)  # simulate latency
        # Seed by route + date + 3-hour bucket, so prices change slowly between scans.
        bucket = datetime.now().strftime("%Y%m%d") + str(datetime.now().hour // 3)
        seed_src = f"{query.destination}{query.depart_date}{query.return_date}{bucket}"
        rng = random.Random(int(hashlib.sha256(seed_src.encode()).hexdigest()[:12], 16))

        base = _BASE_PRICE.get(query.destination, 450.0)
        days_ahead = max((query.depart_date - date.today()).days, 1)
        urgency = 1.35 if days_ahead < 14 else 1.0 if days_ahead < 60 else 0.92
        round_trip = 1.0 if query.return_date else 0.6
        flash_sale = 0.7 if rng.random() < 0.02 else 1.0

        offers: list[FlightOffer] = []
        if query.destination in _DIRECT_FROM_TLV:
            for code, airline in rng.sample(_DIRECT_AIRLINES, k=2):
                price = base * urgency * round_trip * flash_sale * rng.uniform(0.85, 1.25)
                offers.append(self._build(query, price, [(code, airline)], [], rng))
        if query.max_stops >= 1:
            for hub, code, airline in rng.sample(_HUBS, k=3):
                if hub == query.destination:
                    continue
                price = base * urgency * round_trip * flash_sale * rng.uniform(0.7, 1.05)
                offers.append(self._build(query, price, [(code, airline)] * 2, [hub], rng))
        if query.max_stops >= 2:
            (h1, c1, a1), (h2, c2, a2) = rng.sample(_HUBS, k=2)
            if query.destination not in (h1, h2):
                price = base * urgency * round_trip * flash_sale * rng.uniform(0.6, 0.9)
                offers.append(self._build(query, price, [(c1, a1), (c2, a2), (c2, a2)], [h1, h2], rng))
        return sorted(offers, key=lambda o: o.price)

    def _build(
        self,
        query: SearchQuery,
        price: float,
        carriers: list[tuple[str, str]],
        hubs: list[str],
        rng: random.Random,
    ) -> FlightOffer:
        stops = [query.origin, *hubs, query.destination]
        current = datetime.combine(query.depart_date, time(hour=rng.choice([1, 6, 9, 13, 17, 22])))
        segments: list[Segment] = []
        for (code, airline), (src, dst) in zip(carriers, itertools.pairwise(stops), strict=True):
            arrive = current + timedelta(minutes=rng.randint(110, 420))
            segments.append(
                Segment(
                    origin=src,
                    destination=dst,
                    departure=current,
                    arrival=arrive,
                    airline=airline,
                    flight_number=f"{code}{rng.randint(100, 999)}",
                )
            )
            current = arrive + timedelta(minutes=rng.randint(70, 300))
        first_dep = segments[0].departure or current
        last_arr = segments[-1].arrival or current
        return FlightOffer(
            provider=self.name,
            destination_code=query.destination,
            price=round(price, 0),
            currency=query.currency,
            airlines=sorted({s.airline for s in segments}),
            stops=len(hubs),
            outbound=segments,
            depart_date=query.depart_date,
            return_date=query.return_date,
            duration_minutes=int((last_arr - first_dep).total_seconds() // 60),
            booking_url=f"https://www.google.com/travel/flights?q=Flights%20from%20{query.origin}"
            f"%20to%20{query.destination}%20on%20{query.depart_date}",
        )
