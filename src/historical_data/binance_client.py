"""Phase 3 — Binance historical klines client.

Real REST client for Binance's public ``/api/v3/klines`` endpoint — no
API key required for historical market data. Mirrors the existing
``market.coingecko_connector.CoinGeckoConnector``'s async/retry/pacing
pattern for consistency with the rest of the codebase.

This module only fetches and returns raw kline rows — it does not
generate trading signals, compute indicators, or touch any frozen
Strategy Engine / Decision Fusion / Trading Engine code.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.binance.com"
_KLINES_PATH = "/api/v3/klines"
_MAX_LIMIT = 1000  # Binance's max klines per request
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 8.0
_MIN_CALL_INTERVAL_SECONDS = 0.25  # polite pacing, well under Binance's public rate limits

_INTERVAL_SECONDS: dict[str, int] = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800, "12h": 43200,
    "1d": 86400, "3d": 259200, "1w": 604800, "1M": 2592000,
}


class BinanceHistoricalClient:
    """Async client for Binance's public historical klines endpoint.

    Usage::

        async with BinanceHistoricalClient() as client:
            klines = await client.get_klines("BTCUSDT", "1h", start_ms, end_ms)
    """

    def __init__(self, base_url: str = _BASE_URL, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._last_call_time = 0.0

    async def __aenter__(self) -> BinanceHistoricalClient:
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self._timeout)
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = _MAX_LIMIT,
    ) -> list[list[Any]]:
        """Fetch raw klines covering ``[start_time_ms, end_time_ms)``,
        paginating automatically since Binance caps a single request at
        1,000 klines.

        Returns:
            Raw kline rows in Binance's own array format, oldest first:
            ``[open_time_ms, open, high, low, close, volume, close_time_ms, ...]``.
        """
        if interval not in _INTERVAL_SECONDS:
            raise ValueError(f"Unsupported Binance interval: {interval!r}")
        if self._client is None:
            raise RuntimeError("BinanceHistoricalClient must be used as an async context manager")

        all_klines: list[list[Any]] = []
        cursor = start_time_ms
        interval_ms = _INTERVAL_SECONDS[interval] * 1000
        page_limit = min(limit, _MAX_LIMIT)

        while cursor < end_time_ms:
            batch = await self._get_with_retry(
                symbol=symbol, interval=interval, start_time_ms=cursor,
                end_time_ms=end_time_ms, limit=page_limit,
            )
            if not batch:
                break
            all_klines.extend(batch)
            last_open_time = int(batch[-1][0])
            next_cursor = last_open_time + interval_ms
            if next_cursor <= cursor:
                break  # safety against an infinite loop on an unexpected API response
            cursor = next_cursor
            if len(batch) < page_limit:
                break  # fewer than a full page -> reached the end of available data

        return all_klines

    async def _get_with_retry(
        self, *, symbol: str, interval: str, start_time_ms: int, end_time_ms: int, limit: int,
    ) -> list[list[Any]]:
        params = {
            "symbol": symbol.upper(), "interval": interval,
            "startTime": start_time_ms, "endTime": end_time_ms, "limit": limit,
        }
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                elapsed = time.perf_counter() - self._last_call_time
                if elapsed < _MIN_CALL_INTERVAL_SECONDS:
                    await asyncio.sleep(_MIN_CALL_INTERVAL_SECONDS - elapsed)
                resp = await self._client.get(_KLINES_PATH, params=params)
                self._last_call_time = time.perf_counter()
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = min(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), _BACKOFF_MAX_SECONDS)
                    logger.warning(
                        "Binance klines %s %s attempt %d/%d failed: %s — retrying in %.1fs",
                        symbol, interval, attempt, _MAX_RETRIES, exc, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "Binance klines %s %s attempt %d/%d failed: %s — giving up",
                        symbol, interval, attempt, _MAX_RETRIES, exc,
                    )
        raise ConnectionError(f"Binance klines request failed after {_MAX_RETRIES} attempts") from last_exc
