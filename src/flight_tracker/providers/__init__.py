"""Flight data providers.

To add a new source: subclass :class:`FlightProvider`, implement ``search`` and
register it in :func:`create_provider` (plus a value in ``ProviderName``).
"""

from __future__ import annotations

import logging

import httpx

from flight_tracker.config import Config, ProviderName
from flight_tracker.providers.base import (
    FlightProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from flight_tracker.providers.duffel import DuffelProvider
from flight_tracker.providers.mock import MockProvider
from flight_tracker.providers.serpapi import SerpApiProvider
from flight_tracker.providers.travelpayouts import TravelpayoutsProvider

logger = logging.getLogger(__name__)

__all__ = [
    "FlightProvider",
    "ProviderAuthError",
    "ProviderError",
    "ProviderRateLimitError",
    "ProviderUnavailableError",
    "create_provider",
]


def create_provider(config: Config, client: httpx.AsyncClient) -> FlightProvider:
    """Build the provider selected by ``FLIGHT_PROVIDER``; fall back to demo data if no key."""
    match config.flight_provider:
        case ProviderName.SERPAPI if key := config.serpapi_api_key.get_secret_value():
            return SerpApiProvider(client, key)
        case ProviderName.DUFFEL if key := config.duffel_access_token.get_secret_value():
            return DuffelProvider(client, key)
        case ProviderName.TRAVELPAYOUTS if key := config.travelpayouts_token.get_secret_value():
            return TravelpayoutsProvider(client, key)
        case ProviderName.MOCK:
            return MockProvider(client)
        case other:
            logger.warning("No API key configured for provider '%s' - using demo (mock) data", other)
            return MockProvider(client)
