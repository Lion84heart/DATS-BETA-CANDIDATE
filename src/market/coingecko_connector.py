"""DATS — CoinGecko API Connector.

Async connector for the CoinGecko API with rate limiting for free/pro tiers,
exponential-backoff retry, and typed Pydantic returns.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from market.base_connector import BaseDataConnector
from market.schemas import OHLCVBar, PriceTick

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_COINGECKO_API_URL: str = "https://api.coingecko.com/api/v3"
_PRO_COINGECKO_API_URL: str = "https://pro-api.coingecko.com/api/v3"
_MAX_RETRIES: int = 3
_BACKOFF_BASE_SECONDS: float = 1.0
_BACKOFF_MAX_SECONDS: float = 8.0
# Free tier: ~10-30 calls/min; Pro tier: much higher
_FREE_TIER_RATE_LIMIT_PER_MIN: int = 25
_CALL_INTERVAL_SECONDS: float = 60.0 / _FREE_TIER_RATE_LIMIT_PER_MIN  # ~2.4s


class CoinGeckoConnector(BaseDataConnector):
    """Async connector for the CoinGecko API.

    Attributes:
        api_url: Base URL for the CoinGecko API (pro or free).
        api_key: Optional API key for pro-tier access.
        client: Underlying ``httpx.AsyncClient``.
    """

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_key: str | None = api_key
        self.api_url: str = (api_url or (
            _PRO_COINGECKO_API_URL if api_key else _DEFAULT_COINGECKO_API_URL
        )).rstrip("/")
        self._timeout: float = timeout
        self._client: httpx.AsyncClient | None = None
        self._connected: bool = False
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(1)
        self._last_call_time: float = 0.0
        self._call_interval: float = (
            0.1 if api_key else _CALL_INTERVAL_SECONDS
        )  # Pro = fast, free = throttled

    # -- BaseDataConnector implementation ------------------------------------

    @property
    def name(self) -> str:
        return "coingecko"

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    async def connect(self) -> None:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            headers["x-cg-pro-api-key"] = self.api_key

        self._client = httpx.AsyncClient(
            base_url=self.api_url,
            timeout=self._timeout,
            headers=headers,
        )
        self._connected = True
        logger.info(
            "CoinGecko connector connected (url=%s, tier=%s).",
            self.api_url,
            "pro" if self.api_key else "free",
        )

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._connected = False
        logger.info("CoinGecko connector disconnected.")

    async def health_check(self) -> dict[str, Any]:
        if not self.is_connected:
            return {"status": "unhealthy", "error": "not connected", "latency_ms": None}
        import time

        start = time.perf_counter()
        try:
            params: dict[str, Any] = {"ids": "bitcoin", "vs_currencies": "usd"}
            await self._throttled_get("/simple/price", params=params)
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return {"status": "healthy", "latency_ms": latency_ms, "error": None}
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error("CoinGecko health check failed: %s", exc)
            return {"status": "unhealthy", "latency_ms": latency_ms, "error": str(exc)}

    # -- CoinGecko-specific methods ------------------------------------------

    async def get_price(self, ids: list[str]) -> list[PriceTick]:
        """Fetch current prices for a list of CoinGecko coin IDs.

        Args:
            ids: List of CoinGecko coin IDs, e.g. ``["solana", "bitcoin"]``.

        Returns:
            List of ``PriceTick`` objects.

        Raises:
            RuntimeError: If not connected.
            ConnectionError: If all retries are exhausted.
        """
        if not self.is_connected:
            raise RuntimeError("CoinGecko connector not connected — call connect() first.")

        if not ids:
            return []

        params: dict[str, Any] = {
            "ids": ",".join(ids),
            "vs_currencies": "usd",
            "include_24hr_vol": "true",
        }
        data = await self._throttled_get("/simple/price", params=params)

        ticks: list[PriceTick] = []
        for coin_id, info in data.items():
            if not isinstance(info, dict):
                continue
            price = info.get("usd")
            if price is None:
                continue
            try:
                tick = PriceTick(
                    symbol=coin_id,
                    price=float(price),
                    volume=float(info.get("usd_24h_vol", 0) or 0),
                    source="coingecko",
                )
                ticks.append(tick)
            except (ValueError, TypeError) as exc:
                logger.warning("Skipping malformed CoinGecko price for %s: %s", coin_id, exc)

        return ticks

    async def get_ohlcv(
        self,
        id: str,
        vs_currency: str = "usd",
        days: int = 30,
    ) -> list[OHLCVBar]:
        """Fetch OHLCV data for a coin.

        Args:
            id: CoinGecko coin ID, e.g. ``"solana"``.
            vs_currency: Quote currency (default ``"usd"``).
            days: Number of days of data to fetch.

        Returns:
            List of ``OHLCVBar`` objects.

        Raises:
            RuntimeError: If not connected.
            ConnectionError: If all retries are exhausted.
        """
        if not self.is_connected:
            raise RuntimeError("CoinGecko connector not connected — call connect() first.")

        params: dict[str, Any] = {"vs_currency": vs_currency, "days": days}
        data = await self._throttled_get(
            f"/coins/{id}/ohlc",
            params=params,
        )

        bars: list[OHLCVBar] = []
        # CoinGecko returns OHLC as [timestamp, open, high, low, close]
        if isinstance(data, list):
            for row in data:
                if not isinstance(row, (list, tuple)) or len(row) < 5:
                    continue
                try:
                    ts_ms = int(row[0])
                    bar = OHLCVBar(
                        symbol=id,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=0.0,
                        timestamp=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                        interval="daily" if days > 1 else "hourly",
                    )
                    bars.append(bar)
                except (ValueError, TypeError) as exc:
                    logger.warning("Skipping malformed OHLCV row for %s: %s", id, exc)

        return bars

    # -- Internal helpers ----------------------------------------------------

    async def _throttled_get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a rate-limited GET request with exponential-backoff retries.

        Args:
            path: API path (relative to base URL).
            params: Query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            ConnectionError: If all retries are exhausted.
        """
        import time

        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with self._semaphore:
                    # Rate limiting
                    elapsed = time.perf_counter() - self._last_call_time
                    if elapsed < self._call_interval:
                        await asyncio.sleep(self._call_interval - elapsed)

                    resp = await self._client.get(path, params=params)
                    self._last_call_time = time.perf_counter()

                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = min(
                        _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
                        _BACKOFF_MAX_SECONDS,
                    )
                    logger.warning(
                        "CoinGecko GET %s attempt %d/%d failed: %s — retrying in %.1fs",
                        path,
                        attempt,
                        _MAX_RETRIES,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "CoinGecko GET %s attempt %d/%d failed: %s — giving up",
                        path,
                        attempt,
                        _MAX_RETRIES,
                        exc,
                    )
            except Exception as exc:
                last_exc = exc
                logger.error("CoinGecko GET %s unexpected error: %s", path, exc)
                break

        raise ConnectionError(
            f"CoinGecko API request failed after {_MAX_RETRIES} attempts"
        ) from last_exc
