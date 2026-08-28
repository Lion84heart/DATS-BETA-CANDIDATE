"""DATS — Jupiter API Connector.

Async connector for the Jupiter DEX aggregator API with rate limiting,
exponential-backoff retry logic, and typed Pydantic returns.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from market.base_connector import BaseDataConnector
from market.schemas import PriceTick

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_JUPITER_API_URL: str = "https://api.jup.ag"
_MAX_RETRIES: int = 3
_BACKOFF_BASE_SECONDS: float = 1.0
_BACKOFF_MAX_SECONDS: float = 8.0
_RATE_LIMIT_PER_SECOND: int = 10


class JupiterConnector(BaseDataConnector):
    """Async connector for the Jupiter DEX aggregator API.

    Attributes:
        api_url: Base URL for the Jupiter API.
        client: Underlying ``httpx.AsyncClient``.
    """

    def __init__(
        self,
        api_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_url: str = (api_url or _DEFAULT_JUPITER_API_URL).rstrip("/")
        self._timeout: float = timeout
        self._client: httpx.AsyncClient | None = None
        self._connected: bool = False
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(_RATE_LIMIT_PER_SECOND)

    # -- BaseDataConnector implementation ------------------------------------

    @property
    def name(self) -> str:
        return "jupiter"

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    async def connect(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.api_url,
                timeout=self._timeout,
                headers={"Accept": "application/json"},
            )
        self._connected = True
        logger.info("Jupiter connector connected (url=%s).", self.api_url)

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._connected = False
        logger.info("Jupiter connector disconnected.")

    async def health_check(self) -> dict[str, Any]:
        if not self.is_connected:
            return {"status": "unhealthy", "error": "not connected", "latency_ms": None}
        import time

        start = time.perf_counter()
        try:
            async with self._semaphore:
                resp = await self._client.get("/health", timeout=5.0)
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return {
                "status": "healthy" if resp.status_code == 200 else "degraded",
                "latency_ms": latency_ms,
                "error": None,
            }
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error("Jupiter health check failed: %s", exc)
            return {"status": "unhealthy", "latency_ms": latency_ms, "error": str(exc)}

    # -- Jupiter-specific methods --------------------------------------------

    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 50,
    ) -> dict[str, Any]:
        """Fetch a swap quote from Jupiter.

        Args:
            input_mint: Input token mint address.
            output_mint: Output token mint address.
            amount: Amount in lamports / smallest unit.
            slippage_bps: Slippage tolerance in basis points.

        Returns:
            Raw JSON response from Jupiter as a dict.

        Raises:
            RuntimeError: If not connected.
            ConnectionError: If all retries are exhausted.
        """
        if not self.is_connected:
            raise RuntimeError("Jupiter connector not connected — call connect() first.")

        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": slippage_bps,
        }

        return await self._get_with_retry("/swap/v1/quote", params=params)

    async def get_price(self, token_ids: list[str]) -> list[PriceTick]:
        """Fetch current prices for a list of token mint addresses.

        Args:
            token_ids: List of token mint addresses.

        Returns:
            List of ``PriceTick`` objects.

        Raises:
            RuntimeError: If not connected.
            ConnectionError: If all retries are exhausted.
        """
        if not self.is_connected:
            raise RuntimeError("Jupiter connector not connected — call connect() first.")

        if not token_ids:
            return []

        params = {"ids": ",".join(token_ids)}
        data = await self._get_with_retry("/price/v2", params=params)

        ticks: list[PriceTick] = []
        prices = data.get("data", {})
        for token_id, info in prices.items():
            if not isinstance(info, dict):
                continue
            price = info.get("price")
            if price is None:
                continue
            try:
                tick = PriceTick(
                    symbol=token_id,
                    price=float(price),
                    volume=float(info.get("volume24h", 0) or 0),
                    source="jupiter",
                )
                ticks.append(tick)
            except (ValueError, TypeError) as exc:
                logger.warning("Skipping malformed Jupiter price for %s: %s", token_id, exc)

        return ticks

    # -- Internal helpers ----------------------------------------------------

    async def _get_with_retry(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GET request with exponential-backoff retries.

        Args:
            path: API path (relative to base URL).
            params: Query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            ConnectionError: If all retries are exhausted.
        """
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with self._semaphore:
                    resp = await self._client.get(path, params=params)
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
                        "Jupiter GET %s attempt %d/%d failed: %s — retrying in %.1fs",
                        path,
                        attempt,
                        _MAX_RETRIES,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "Jupiter GET %s attempt %d/%d failed: %s — giving up",
                        path,
                        attempt,
                        _MAX_RETRIES,
                        exc,
                    )
            except Exception as exc:
                last_exc = exc
                logger.error("Jupiter GET %s unexpected error: %s", path, exc)
                break

        raise ConnectionError(
            f"Jupiter API request failed after {_MAX_RETRIES} attempts"
        ) from last_exc
