"""DATS — Async Redis Client Manager.

Provides a ``RedisManager`` wrapper around ``redis.asyncio.Redis`` with
connection lifecycle management, JSON serialization, retry logic, and a
health-check endpoint.

Example::

    from infra.config import get_config
    from infra.redis_client import RedisManager

    cfg = get_config()
    redis_mgr = RedisManager(cfg.redis)
    await redis_mgr.connect()

    await redis_mgr.set("key", {"foo": "bar"}, ttl=300)
    value = await redis_mgr.get("key")  # → {"foo": "bar"}

    await redis_mgr.close()
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from redis.asyncio import Redis, from_url
from redis.asyncio.connection import ConnectionPool

from infra.config import RedisConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_RETRIES: int = 3
_BACKOFF_BASE_SECONDS: float = 1.0
_BACKOFF_MAX_SECONDS: float = 8.0
_DEFAULT_TTL: int = 3600  # 1 hour


# ---------------------------------------------------------------------------
# RedisManager
# ---------------------------------------------------------------------------


class RedisManager:
    """Async Redis client manager with retry, JSON support, and health checks.

    Attributes:
        config: ``RedisConfig`` instance.
        client: The underlying ``redis.asyncio.Redis`` instance (``None``
            until ``connect()`` is called).
    """

    def __init__(self, config: RedisConfig) -> None:
        self.config: RedisConfig = config
        self.client: Redis | None = None
        self._pool: ConnectionPool | None = None

    # -- Connection lifecycle ------------------------------------------------

    async def connect(self) -> Redis:
        """Establish the Redis connection with retry logic.

        Returns:
            The connected ``Redis`` client.

        Raises:
            ConnectionError: If all retry attempts are exhausted.
        """
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                # Build DSN for from_url
                auth = ""
                if self.config.password:
                    auth = f":{self.config.password}@"

                dsn = (
                    f"redis://{auth}{self.config.host}:{self.config.port}"
                    f"/{self.config.db}"
                )

                self.client = from_url(
                    dsn,
                    decode_responses=self.config.decode_responses,
                    socket_timeout=self.config.socket_timeout,
                    socket_connect_timeout=self.config.socket_connect_timeout,
                    health_check_interval=self.config.health_check_interval,
                    max_connections=self.config.max_connections,
                )
                # Verify connectivity with a PING
                await self.client.ping()
                logger.info(
                    "Redis connected to %s:%d/%d",
                    self.config.host,
                    self.config.port,
                    self.config.db,
                )
                return self.client
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = min(
                        _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
                        _BACKOFF_MAX_SECONDS,
                    )
                    logger.warning(
                        "Redis connection attempt %d/%d failed: %s — retrying in %.1fs",
                        attempt,
                        _MAX_RETRIES,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "Redis connection attempt %d/%d failed: %s — giving up",
                        attempt,
                        _MAX_RETRIES,
                        exc,
                    )

        raise ConnectionError(
            f"Failed to connect to Redis after {_MAX_RETRIES} attempts"
        ) from last_exc

    async def close(self) -> None:
        """Gracefully close the Redis connection and pool.

        Idempotent — safe to call multiple times.
        """
        if self.client is not None:
            await self.client.close()
            self.client = None
            logger.info("Redis connection closed.")

        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None
            logger.debug("Redis connection pool disconnected.")

    # -- Core key/value operations ------------------------------------------

    async def get(self, key: str) -> Any | None:
        """Fetch and JSON-deserialize a value by *key*.

        Returns:
            The deserialized Python object, or ``None`` if the key does not
            exist or the client is not connected.
        """
        if self.client is None:
            logger.warning("Redis get() called before connect()")
            return None

        raw: str | None = await self.client.get(key)
        if raw is None:
            return None

        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Redis key %r is not valid JSON (%s) — returning raw.", key, exc)
            return raw

    async def set(
        self,
        key: str,
        value: Any,
        *,
        ttl: int | None = _DEFAULT_TTL,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """JSON-serialize and store *value* under *key*.

        Args:
            key: Redis key.
            value: Any JSON-serialisable Python object.
            ttl: Time-to-live in seconds (``None`` → no expiry).
            nx: Only set if the key does **not** exist.
            xx: Only set if the key **already** exists.

        Returns:
            ``True`` if the key was set, ``False`` otherwise.
        """
        if self.client is None:
            logger.warning("Redis set() called before connect()")
            return False

        try:
            payload: str = json.dumps(value, default=str)
        except (TypeError, ValueError) as exc:
            logger.error("Failed to JSON-serialise value for key %r: %s", key, exc)
            return False

        result = await self.client.set(key, payload, ex=ttl, nx=nx, xx=xx)
        return bool(result)

    async def delete(self, key: str) -> int:
        """Delete *key* from Redis.

        Returns:
            Number of keys removed (``0`` or ``1`` for a single key).
        """
        if self.client is None:
            logger.warning("Redis delete() called before connect()")
            return 0

        return await self.client.delete(key)

    async def exists(self, key: str) -> bool:
        """Check whether *key* exists.

        Returns:
            ``True`` if the key exists, ``False`` otherwise.
        """
        if self.client is None:
            logger.warning("Redis exists() called before connect()")
            return False

        count: int = await self.client.exists(key)
        return count > 0

    # -- Additional utilities ------------------------------------------------

    async def ttl(self, key: str) -> int:
        """Return the remaining TTL for *key* in seconds.

        Returns ``-2`` if the key does not exist, ``-1`` if it has no
        expiry, or a positive integer otherwise.
        """
        if self.client is None:
            logger.warning("Redis ttl() called before connect()")
            return -2
        return await self.client.ttl(key)

    async def expire(self, key: str, seconds: int) -> bool:
        """Set (or update) the TTL on *key*.

        Returns:
            ``True`` on success, ``False`` if the key does not exist.
        """
        if self.client is None:
            logger.warning("Redis expire() called before connect()")
            return False
        return await self.client.expire(key, seconds)

    async def keys(self, pattern: str = "*") -> list[str]:
        """Return a list of keys matching *pattern* (use sparingly in production)."""
        if self.client is None:
            logger.warning("Redis keys() called before connect()")
            return []
        return list(await self.client.keys(pattern))

    # -- Health check --------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Execute a ``PING`` health probe.

        Returns:
            Dictionary with ``status``, ``latency_ms``, and optional
            ``error`` fields.
        """
        import time

        if self.client is None:
            return {"status": "unhealthy", "error": "not connected", "latency_ms": None}

        start = time.perf_counter()
        try:
            pong = await self.client.ping()
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return {
                "status": "healthy" if pong else "degraded",
                "latency_ms": latency_ms,
                "error": None,
            }
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error("Redis health check failed: %s", exc)
            return {"status": "unhealthy", "latency_ms": latency_ms, "error": str(exc)}

    # -- Context-manager support ---------------------------------------------

    async def __aenter__(self) -> RedisManager:
        await self.connect()
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.close()
