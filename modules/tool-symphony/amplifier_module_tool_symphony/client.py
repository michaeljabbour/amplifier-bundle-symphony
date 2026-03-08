"""HTTP client for Symphony's REST API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

_BACKOFFS: list[float] = [1.0, 2.0, 4.0]  # seconds between retries
_MAX_ATTEMPTS: int = len(_BACKOFFS) + 1  # 1 initial + 3 retries
_RETRY_STATUSES: frozenset[int] = frozenset({503, 429})


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class SymphonyError(Exception):
    """Raised when a Symphony API request fails."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class SymphonyClient:
    """Async HTTP client for the Symphony orchestration service.

    The underlying :class:`httpx.AsyncClient` is created lazily on the first
    request so that constructing a :class:`SymphonyClient` is always cheap and
    never raises.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        connect_timeout: float = 5.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._connect_timeout = connect_timeout
        self._http: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_status(self) -> dict[str, Any]:
        """GET /api/v1/state → parsed response body."""
        return await self._request("GET", "/api/v1/state")

    async def get_issue(self, identifier: str) -> dict[str, Any]:
        """GET /api/v1/{identifier} → parsed response body."""
        return await self._request("GET", f"/api/v1/{identifier}")

    async def refresh(self) -> dict[str, Any]:
        """POST /api/v1/refresh → parsed response body."""
        return await self._request("POST", "/api/v1/refresh")

    async def close(self) -> None:
        """Close the underlying HTTP client.  Safe to call more than once."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_client(self) -> httpx.AsyncClient:
        """Return the shared AsyncClient, creating it on first call."""
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout, connect=self._connect_timeout)
            )
        return self._http

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Send *method* to *path* with automatic retry on transient failures.

        Retry policy
        ------------
        * Up to :data:`_MAX_ATTEMPTS` total attempts (1 initial + 3 retries).
        * Exponential back-off :data:`_BACKOFFS` between attempts.
        * Retryable:  503, 429, :class:`httpx.ConnectError`,
          :class:`httpx.TimeoutException`.
        * Immediate raise (no retry): 404, all other 4xx.
        """
        url = f"{self._base_url}{path}"
        client = self._ensure_client()
        last_exc: Exception | None = None

        for attempt in range(_MAX_ATTEMPTS):
            # ---- send -------------------------------------------------------
            try:
                response = await client.request(method, url, **kwargs)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                logger.warning(
                    "Attempt %d/%d — transport error: %s",
                    attempt + 1,
                    _MAX_ATTEMPTS,
                    exc,
                )
                if attempt < len(_BACKOFFS):
                    await asyncio.sleep(_BACKOFFS[attempt])
                continue  # → next attempt

            # ---- inspect status code ----------------------------------------
            status = response.status_code

            # Non-retryable client errors — fail immediately.
            if status == 404:
                raise SymphonyError(f"Not found: {url}", status_code=status)
            if 400 <= status < 500 and status not in _RETRY_STATUSES:
                raise SymphonyError(
                    f"Client error {status} from {url}", status_code=status
                )

            # Success.
            if response.is_success:
                return response.json()  # type: ignore[no-any-return]

            # Retryable server error (503, 429, …).
            last_exc = SymphonyError(f"HTTP {status} from {url}", status_code=status)
            logger.warning(
                "Attempt %d/%d — retryable status %d",
                attempt + 1,
                _MAX_ATTEMPTS,
                status,
            )
            if attempt < len(_BACKOFFS):
                await asyncio.sleep(_BACKOFFS[attempt])
            # → next attempt

        # All attempts exhausted.
        if isinstance(last_exc, SymphonyError):
            raise last_exc
        raise SymphonyError(str(last_exc)) from last_exc
