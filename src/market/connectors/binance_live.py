"""Live Binance market-data connector for real-time paper trading.

Polls Binance's public ``/api/v3/ticker/bookTicker`` endpoint (best
bid/ask, no API key required — this is public market data, not an
authenticated trading endpoint) for real BTCUSDT/ETHUSDT/SOLUSDT
prices, and turns them into the exact same ``PriceTick`` shape
``SimulatedConnector`` already produces, so it's a drop-in replacement
that feeds the existing broker/AI-engine callback pipeline unchanged.

This connector is structurally incapable of placing a real trade: it
only ever issues GET requests to a public, unauthenticated market-data
endpoint. No API key, secret, or signed request appears anywhere in
this module.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from market.connectors.base import MarketDataConnector, PriceTick

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.binance.com"
_BOOK_TICKER_PATH = "/api/v3/ticker/bookTicker"
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 8.0


class BinanceLiveConnector(MarketDataConnector):
    """Real-time (REST-polled) Binance market data connector.

    Usage mirrors ``SimulatedConnector`` exactly — register with
    ``FeedManager``, then ``connect()`` + ``subscribe(symbols)``.
    """

    def __init__(self, tick_interval: float = 30.0, buffer_size: int = 1000, timeout: float = 15.0):
        """Args:
            tick_interval: Seconds between polls. 30s is a deliberate,
                un-tuned default — frequent enough to be "continuous,"
                infrequent enough to be trivially safe against Binance's
                public rate limits over a multi-day run, and each poll
                becomes one bar for the Strategy Engine (the same
                tick-as-bar convention already used for the simulated
                feed), so the interval also sets the bot's effective
                bar granularity.
        """
        super().__init__(name="binance_live", buffer_size=buffer_size)
        self._tick_interval = tick_interval
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _connect_impl(self) -> bool:
        self._client = httpx.AsyncClient(base_url=_BASE_URL, timeout=self._timeout)
        try:
            resp = await self._client.get("/api/v3/ping")
            resp.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.error("Binance live connector failed initial ping: %s", exc)
            return False

    async def _disconnect_impl(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _subscribe_impl(self, symbols: list[str]) -> None:
        pass  # nothing to do — the next poll picks up newly-subscribed symbols

    async def _unsubscribe_impl(self, symbols: list[str]) -> None:
        pass

    async def _poll_impl(self) -> None:
        if not self._subscribed or self._client is None:
            await asyncio.sleep(self._tick_interval)
            return

        symbols = sorted(self._subscribed)
        rows = await self._fetch_book_tickers(symbols)
        if rows is not None:
            for row in rows:
                try:
                    symbol = row["symbol"]
                    if symbol not in self._subscribed:
                        continue
                    bid, ask = float(row["bidPrice"]), float(row["askPrice"])
                    mid = (bid + ask) / 2.0
                    tick = PriceTick(
                        symbol=symbol, timestamp=time.time(), price=mid,
                        bid=bid, ask=ask, volume=0.0, source="binance_live",
                    )
                    self._notify(tick)
                except (KeyError, ValueError, TypeError) as exc:
                    logger.warning("Skipping malformed bookTicker row for %r: %s", row, exc)

        await asyncio.sleep(self._tick_interval)

    async def _fetch_book_tickers(self, symbols: list[str]) -> list[dict] | None:
        """Fetch best bid/ask for every subscribed symbol in one batched
        request, with retry/backoff. Returns ``None`` (not raises) after
        exhausting retries, so one bad polling cycle never kills the
        connector's dispatch loop — it just tries again next cycle."""
        params = {"symbols": "[" + ",".join(f'"{s}"' for s in symbols) + "]"}
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = await self._client.get(_BOOK_TICKER_PATH, params=params)
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = min(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), _BACKOFF_MAX_SECONDS)
                    logger.warning(
                        "Binance live bookTicker poll attempt %d/%d failed: %s — retrying in %.1fs",
                        attempt, _MAX_RETRIES, exc, wait,
                    )
                    await asyncio.sleep(wait)
        logger.error("Binance live bookTicker poll failed after %d attempts: %s", _MAX_RETRIES, last_exc)
        return None

    def is_available(self) -> bool:
        return self._client is not None
