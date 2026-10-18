"""Broad destination regions. A tracked region expands into several airports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Region:
    key: str
    name: str
    airports: tuple[str, ...]


REGIONS: dict[str, Region] = {
    region.key: region
    for region in (
        Region("EUROPE", "אירופה", ("LHR", "CDG", "FCO", "BCN", "ATH", "BUD", "PRG", "BER", "AMS", "VIE")),
        Region("USA", 'ארה"ב', ("JFK", "EWR", "LAX", "MIA", "BOS", "SFO")),
        Region("ASIA", "אסיה", ("BKK", "HKT", "DEL", "BOM", "NRT", "SIN")),
        Region("EAST_EUROPE", "מזרח אירופה", ("OTP", "SOF", "WAW", "KRK", "TBS", "BEG")),
        Region("GREECE_CYPRUS", "יוון וקפריסין", ("ATH", "SKG", "HER", "RHO", "LCA", "PFO")),
    )
}

# Friendly Hebrew names for common airports (used by the UI and in alerts).
AIRPORT_NAMES: dict[str, str] = {
    "LHR": "לונדון",
    "CDG": "פריז",
    "FCO": "רומא",
    "BCN": "ברצלונה",
    "ATH": "אתונה",
    "BUD": "בודפשט",
    "PRG": "פראג",
    "BER": "ברלין",
    "AMS": "אמסטרדם",
    "VIE": "וינה",
    "JFK": "ניו יורק",
    "EWR": "ניוארק",
    "LAX": "לוס אנג'לס",
    "MIA": "מיאמי",
    "BOS": "בוסטון",
    "SFO": "סן פרנסיסקו",
    "BKK": "בנגקוק",
    "HKT": "פוקט",
    "DEL": "דלהי",
    "BOM": "מומבאי",
    "NRT": "טוקיו",
    "SIN": "סינגפור",
    "OTP": "בוקרשט",
    "SOF": "סופיה",
    "WAW": "ורשה",
    "KRK": "קרקוב",
    "TBS": "טביליסי",
    "BEG": "בלגרד",
    "SKG": "סלוניקי",
    "HER": "כרתים",
    "RHO": "רודוס",
    "LCA": "לרנקה",
    "PFO": "פאפוס",
    "MXP": "מילאנו",
    "MAD": "מדריד",
    "LIS": "ליסבון",
    "DXB": "דובאי",
    "IST": "איסטנבול",
    "MUC": "מינכן",
    "FRA": "פרנקפורט",
    "ZRH": "ציריך",
    "TLV": "תל אביב",
}


def is_region(code: str) -> bool:
    return code.upper() in REGIONS


def airports_for(code: str) -> tuple[str, ...]:
    """Return the airports to search for a destination code (region or single IATA)."""
    upper = code.upper()
    region = REGIONS.get(upper)
    return region.airports if region else (upper,)


def display_name(code: str) -> str:
    upper = code.upper()
    region = REGIONS.get(upper)
    if region:
        return region.name
    return AIRPORT_NAMES.get(upper, upper)
