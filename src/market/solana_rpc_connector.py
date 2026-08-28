"""DATS — Solana JSON-RPC Connector.

Async connector for Solana JSON-RPC endpoints with retry logic and
strongly-typed return values.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from market.base_connector import BaseDataConnector

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_SOLANA_RPC_URL: str = "https://api.mainnet-beta.solana.com"
_MAX_RETRIES: int = 3
_BACKOFF_BASE_SECONDS: float = 1.0
_BACKOFF_MAX_SECONDS: float = 8.0
_RATE_LIMIT_PER_SECOND: int = 10


class SolanaRpcConnector(BaseDataConnector):
    """Async connector for Solana JSON-RPC API.

    Attributes:
        rpc_url: Solana RPC endpoint URL.
        client: Underlying ``httpx.AsyncClient``.
    """

    def __init__(
        self,
        rpc_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.rpc_url: str = (rpc_url or _DEFAULT_SOLANA_RPC_URL).rstrip("/")
        self._timeout: float = timeout
        self._client: httpx.AsyncClient | None = None
        self._connected: bool = False
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(_RATE_LIMIT_PER_SECOND)
        self._request_id: int = 0

    # -- BaseDataConnector implementation ------------------------------------

    @property
    def name(self) -> str:
        return "solana_rpc"

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    async def connect(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.rpc_url,
                timeout=self._timeout,
                headers={"Content-Type": "application/json"},
            )
        self._connected = True
        logger.info("Solana RPC connector connected (url=%s).", self.rpc_url)

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._connected = False
        logger.info("Solana RPC connector disconnected.")

    async def health_check(self) -> dict[str, Any]:
        if not self.is_connected:
            return {"status": "unhealthy", "error": "not connected", "latency_ms": None}
        import time

        start = time.perf_counter()
        try:
            result = await self._rpc_call("getHealth", [])
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            is_healthy = result == "ok"
            return {
                "status": "healthy" if is_healthy else "degraded",
                "latency_ms": latency_ms,
                "error": None if is_healthy else f"RPC health: {result}",
            }
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error("Solana RPC health check failed: %s", exc)
            return {"status": "unhealthy", "latency_ms": latency_ms, "error": str(exc)}

    # -- Solana-specific methods ---------------------------------------------

    async def get_account_info(self, pubkey: str) -> dict[str, Any]:
        """Fetch account information for a Solana public key.

        Args:
            pubkey: Base-58 encoded public key.

        Returns:
            Parsed JSON-RPC result.

        Raises:
            RuntimeError: If not connected.
            ConnectionError: If all retries are exhausted.
        """
        if not self.is_connected:
            raise RuntimeError("Solana RPC connector not connected — call connect() first.")

        return await self._rpc_call("getAccountInfo", [pubkey, {"encoding": "jsonParsed"}])

    async def get_token_accounts(
        self,
        owner: str,
        program_id: str = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    ) -> list[dict[str, Any]]:
        """Fetch token accounts owned by an address.

        Args:
            owner: Owner's base-58 public key.
            program_id: Token program ID (default SPL Token).

        Returns:
            List of token account objects.

        Raises:
            RuntimeError: If not connected.
            ConnectionError: If all retries are exhausted.
        """
        if not self.is_connected:
            raise RuntimeError("Solana RPC connector not connected — call connect() first.")

        result = await self._rpc_call(
            "getTokenAccountsByOwner",
            [
                owner,
                {"programId": program_id},
                {"encoding": "jsonParsed"},
            ],
        )
        if isinstance(result, dict):
            return result.get("value", [])
        return []

    async def get_signatures_for_address(
        self,
        address: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch recent transaction signatures for an address.

        Args:
            address: Base-58 encoded address.
            limit: Maximum number of signatures (default 10, max 1000).

        Returns:
            List of signature info dicts.

        Raises:
            RuntimeError: If not connected.
            ConnectionError: If all retries are exhausted.
        """
        if not self.is_connected:
            raise RuntimeError("Solana RPC connector not connected — call connect() first.")

        result = await self._rpc_call(
            "getSignaturesForAddress",
            [address, {"limit": limit}],
        )
        return result if isinstance(result, list) else []

    async def get_transaction(self, signature: str) -> dict[str, Any]:
        """Fetch a transaction by its signature.

        Args:
            signature: Base-58 encoded transaction signature.

        Returns:
            Transaction object.

        Raises:
            RuntimeError: If not connected.
            ConnectionError: If all retries are exhausted.
        """
        if not self.is_connected:
            raise RuntimeError("Solana RPC connector not connected — call connect() first.")

        return await self._rpc_call(
            "getTransaction",
            [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
        )

    # -- Internal helpers ----------------------------------------------------

    async def _rpc_call(self, method: str, params: list[Any]) -> Any:
        """Execute a JSON-RPC call with exponential-backoff retries.

        Args:
            method: JSON-RPC method name.
            params: Method parameters.

        Returns:
            Parsed ``result`` field from the JSON-RPC response.

        Raises:
            ConnectionError: If all retries are exhausted.
            RuntimeError: If the RPC returns an error.
        """
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with self._semaphore:
                    resp = await self._client.post("", json=payload)
                resp.raise_for_status()

                data = resp.json()
                if "error" in data and data["error"] is not None:
                    err = data["error"]
                    raise RuntimeError(f"Solana RPC error: {err}")

                return data.get("result")
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = min(
                        _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
                        _BACKOFF_MAX_SECONDS,
                    )
                    logger.warning(
                        "Solana RPC %s attempt %d/%d failed: %s — retrying in %.1fs",
                        method,
                        attempt,
                        _MAX_RETRIES,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "Solana RPC %s attempt %d/%d failed: %s — giving up",
                        method,
                        attempt,
                        _MAX_RETRIES,
                        exc,
                    )
            except RuntimeError:
                raise
            except Exception as exc:
                last_exc = exc
                logger.error("Solana RPC %s unexpected error: %s", method, exc)
                break

        raise ConnectionError(
            f"Solana RPC call failed after {_MAX_RETRIES} attempts"
        ) from last_exc
