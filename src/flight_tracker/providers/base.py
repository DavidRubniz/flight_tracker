"""Common provider interface, error types and a resilient HTTP helper."""

from __future__ import annotations

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from typing import Any, ClassVar

import httpx

from flight_tracker.models import SearchQuery, SearchResult

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Generic failure while fetching data from a provider."""


class ProviderAuthError(ProviderError):
    """Invalid / missing credentials. Retrying will not help."""


class ProviderRateLimitError(ProviderError):
    """The provider throttled us (HTTP 429) even after retries."""


class ProviderUnavailableError(ProviderError):
    """Network failure, timeout or repeated 5xx responses."""


class FlightProvider(ABC):
    name: ClassVar[str] = "base"
    max_retries: ClassVar[int] = 3

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @abstractmethod
    async def search(self, query: SearchQuery) -> SearchResult:
        """Return offers (possibly none) and, if the source has them, price insights."""

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str | int] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Perform an HTTP request with retries + exponential backoff and map errors."""
        last_error: str = "unknown error"
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self._client.request(
                    method, url, params=params, json=json_body, headers=headers
                )
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                last_error = f"network error: {exc.__class__.__name__}: {exc}"
                logger.warning("[%s] %s (attempt %d/%d)", self.name, last_error, attempt, self.max_retries)
                await self._backoff(attempt)
                continue

            status = response.status_code
            if status in (401, 403):
                raise ProviderAuthError(f"{self.name}: authentication failed (HTTP {status})")
            if status == 429:
                last_error = "rate limited (HTTP 429)"
                retry_after = response.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else None
                logger.warning("[%s] %s (attempt %d/%d)", self.name, last_error, attempt, self.max_retries)
                if attempt == self.max_retries:
                    raise ProviderRateLimitError(f"{self.name}: {last_error}")
                await self._backoff(attempt, delay)
                continue
            if status >= 500:
                last_error = f"server error HTTP {status}"
                logger.warning("[%s] %s (attempt %d/%d)", self.name, last_error, attempt, self.max_retries)
                await self._backoff(attempt)
                continue
            if status >= 400:
                raise ProviderError(f"{self.name}: HTTP {status}: {response.text[:300]}")

            try:
                payload = response.json()
            except ValueError as exc:
                raise ProviderError(f"{self.name}: invalid JSON response") from exc
            if not isinstance(payload, dict):
                raise ProviderError(f"{self.name}: unexpected response shape")
            return payload

        raise ProviderUnavailableError(f"{self.name}: {last_error}")

    @staticmethod
    async def _backoff(attempt: int, explicit_delay: float | None = None) -> None:
        delay = explicit_delay if explicit_delay is not None else (2**attempt) + random.uniform(0, 1)
        await asyncio.sleep(min(delay, 30.0))
