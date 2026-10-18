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
    "ProviderConfigError",
    "ProviderError",
    "ProviderRateLimitError",
    "ProviderUnavailableError",
    "create_provider",
    "provider_key",
]


class ProviderConfigError(Exception):
    """The selected provider is missing its API key."""


def provider_key(config: Config) -> str:
    """Return the API key of the selected provider ("" for the demo provider).

    A real provider without a key is a hard error rather than a silent fallback to
    demo data - otherwise fake prices would end up in the real price history.
    """
    keys = {
        ProviderName.SERPAPI: ("SERPAPI_API_KEY", config.serpapi_api_key),
        ProviderName.DUFFEL: ("DUFFEL_ACCESS_TOKEN", config.duffel_access_token),
        ProviderName.TRAVELPAYOUTS: ("TRAVELPAYOUTS_TOKEN", config.travelpayouts_token),
    }
    if config.flight_provider is ProviderName.MOCK:
        return ""
    env_name, secret = keys[config.flight_provider]
    if not (key := secret.get_secret_value().strip()):
        raise ProviderConfigError(
            f"FLIGHT_PROVIDER={config.flight_provider} but {env_name} is empty in .env - "
            "add the key, or set FLIGHT_PROVIDER=mock for demo data"
        )
    return key


def create_provider(config: Config, client: httpx.AsyncClient) -> FlightProvider:
    """Build the provider selected by ``FLIGHT_PROVIDER``."""
    key = provider_key(config)
    match config.flight_provider:
        case ProviderName.MOCK:
            logger.info("Using demo (mock) flight data")
            return MockProvider(client)
        case ProviderName.SERPAPI:
            return SerpApiProvider(client, key)
        case ProviderName.DUFFEL:
            return DuffelProvider(client, key)
        case ProviderName.TRAVELPAYOUTS:
            return TravelpayoutsProvider(client, key)
