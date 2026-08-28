"""Tests for ``src.infra.redis_client`` — Async Redis Client Manager.

All external I/O is mocked so these tests run without a real Redis
instance.  Coverage targets:
* Connection lifecycle (connect / close)
* Retry logic on connection failure
* Core operations: get, set, delete, exists
* JSON serialisation / deserialisation
* TTL and expiry helpers
* Health check (healthy / unhealthy)
* Context-manager entry/exit
* Calling operations before connect() returns safe defaults.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infra.config import RedisConfig
from src.infra.redis_client import (
    _BACKOFF_MAX_SECONDS,
    _MAX_RETRIES,
    RedisManager,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def redis_config() -> RedisConfig:
    return RedisConfig(
        host="test-redis",
        port=6380,
        db=1,
        password="test-pass",
        decode_responses=True,
        socket_timeout=10,
    )


@pytest.fixture
def manager(redis_config: RedisConfig) -> RedisManager:
    return RedisManager(redis_config)


@pytest.fixture
def mock_client() -> MagicMock:
    """A mock redis.asyncio.Redis with async methods."""
    client = MagicMock()
    client.ping = AsyncMock(return_value=True)
    client.get = AsyncMock()
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.exists = AsyncMock(return_value=1)
    client.ttl = AsyncMock(return_value=300)
    client.expire = AsyncMock(return_value=True)
    client.keys = AsyncMock(return_value=["key1", "key2"])
    client.close = AsyncMock()
    return client


# ===========================================================================
# Connection lifecycle
# ===========================================================================


@pytest.mark.unit
class TestConnect:
    """Tests for ``RedisManager.connect``."""

    @pytest.mark.asyncio
    async def test_success(self, manager: RedisManager, mock_client: MagicMock) -> None:
        with patch("src.infra.redis_client.from_url", return_value=mock_client):
            result = await manager.connect()

        assert result is mock_client
        assert manager.client is mock_client
        mock_client.ping.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dsn_with_password(self, manager: RedisManager, mock_client: MagicMock) -> None:
        with patch("src.infra.redis_client.from_url") as mock_from_url:
            mock_from_url.return_value = mock_client
            await manager.connect()

        dsn = mock_from_url.call_args[0][0]
        assert dsn == "redis://:test-pass@test-redis:6380/1"

    @pytest.mark.asyncio
    async def test_dsn_without_password(self) -> None:
        cfg = RedisConfig(host="localhost", port=6379, db=0, password=None)
        mgr = RedisManager(cfg)
        mock_client = MagicMock()
        mock_client.ping = AsyncMock(return_value=True)

        with patch("src.infra.redis_client.from_url") as mock_from_url:
            mock_from_url.return_value = mock_client
            await mgr.connect()

        dsn = mock_from_url.call_args[0][0]
        assert dsn == "redis://localhost:6379/0"

    @pytest.mark.asyncio
    async def test_retry_then_success(self, manager: RedisManager) -> None:
        mock_client = MagicMock()
        mock_client.ping = AsyncMock(return_value=True)

        with patch("src.infra.redis_client.from_url") as mock_from_url:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_from_url.side_effect = [
                    ConnectionError("fail 1"),
                    ConnectionError("fail 2"),
                    mock_client,
                ]

                result = await manager.connect()

                assert result is mock_client
                assert mock_from_url.call_count == 3
                assert mock_sleep.call_count == 2
                mock_sleep.assert_any_call(1.0)
                mock_sleep.assert_any_call(2.0)

    @pytest.mark.asyncio
    async def test_retry_exhausted(self, manager: RedisManager) -> None:
        with patch("src.infra.redis_client.from_url") as mock_from_url:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                mock_from_url.side_effect = ConnectionError("always fails")

                with pytest.raises(ConnectionError, match="Failed to connect to Redis"):
                    await manager.connect()

                assert mock_from_url.call_count == _MAX_RETRIES

    @pytest.mark.asyncio
    async def test_backoff_capped(self, manager: RedisManager) -> None:
        with patch("src.infra.redis_client.from_url") as mock_from_url:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_client = MagicMock()
                mock_client.ping = AsyncMock(return_value=True)
                mock_from_url.side_effect = [
                    ConnectionError(f"fail {i}") for i in range(_MAX_RETRIES - 1)
                ] + [mock_client]

                await manager.connect()
                for call in mock_sleep.call_args_list:
                    wait_time = call[0][0]
                    assert wait_time <= _BACKOFF_MAX_SECONDS


@pytest.mark.unit
class TestClose:
    """Tests for ``RedisManager.close``."""

    @pytest.mark.asyncio
    async def test_close(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        await manager.close()
        mock_client.close.assert_awaited_once()
        assert manager.client is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self, manager: RedisManager) -> None:
        mock_client = MagicMock()
        mock_client.close = AsyncMock()
        manager.client = mock_client

        await manager.close()
        await manager.close()
        mock_client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_no_client(self, manager: RedisManager) -> None:
        await manager.close()  # should not raise


# ===========================================================================
# Core operations
# ===========================================================================


@pytest.mark.unit
class TestGet:
    """Tests for ``RedisManager.get``."""

    @pytest.mark.asyncio
    async def test_get_json_value(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        mock_client.get.return_value = '{"foo": "bar", "count": 42}'

        result = await manager.get("mykey")

        assert result == {"foo": "bar", "count": 42}
        mock_client.get.assert_awaited_once_with("mykey")

    @pytest.mark.asyncio
    async def test_get_missing_key(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        mock_client.get.return_value = None

        result = await manager.get("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_non_json_returns_raw(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        mock_client.get.return_value = "plain-string-value"

        result = await manager.get("rawkey")
        assert result == "plain-string-value"

    @pytest.mark.asyncio
    async def test_get_before_connect(self, manager: RedisManager) -> None:
        result = await manager.get("key")
        assert result is None


@pytest.mark.unit
class TestSet:
    """Tests for ``RedisManager.set``."""

    @pytest.mark.asyncio
    async def test_set_json_serialisable(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        value = {"signal": "buy", "ticker": "AAPL", "price": 175.5}

        result = await manager.set("trade:1", value, ttl=300)

        assert result is True
        mock_client.set.assert_awaited_once()
        call_args = mock_client.set.call_args
        # set(key, payload, ex=ttl, nx=nx, xx=xx)
        assert call_args[0][0] == "trade:1"  # key
        stored = json.loads(call_args[0][1])  # payload
        assert stored == value
        assert call_args.kwargs["ex"] == 300

    @pytest.mark.asyncio
    async def test_set_with_nx(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        await manager.set("key", "val", nx=True)
        call_args = mock_client.set.call_args
        assert call_args.kwargs["nx"] is True

    @pytest.mark.asyncio
    async def test_set_with_xx(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        await manager.set("key", "val", xx=True)
        call_args = mock_client.set.call_args
        assert call_args.kwargs["xx"] is True

    @pytest.mark.asyncio
    async def test_set_no_ttl(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        await manager.set("key", "val", ttl=None)
        call_args = mock_client.set.call_args
        assert call_args.kwargs["ex"] is None

    @pytest.mark.asyncio
    async def test_set_before_connect(self, manager: RedisManager) -> None:
        result = await manager.set("key", "val")
        assert result is False

    @pytest.mark.asyncio
    async def test_set_non_serialisable(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client

        # Create an object whose __str__ raises, bypassing json.dumps default=str
        class BadObject:
            def __str__(self) -> str:
                raise TypeError("Cannot convert to string")

        result = await manager.set("key", BadObject())
        assert result is False
        mock_client.set.assert_not_awaited()


@pytest.mark.unit
class TestDelete:
    """Tests for ``RedisManager.delete``."""

    @pytest.mark.asyncio
    async def test_delete_existing(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        result = await manager.delete("key")
        assert result == 1
        mock_client.delete.assert_awaited_once_with("key")

    @pytest.mark.asyncio
    async def test_delete_before_connect(self, manager: RedisManager) -> None:
        result = await manager.delete("key")
        assert result == 0


@pytest.mark.unit
class TestExists:
    """Tests for ``RedisManager.exists``."""

    @pytest.mark.asyncio
    async def test_exists_true(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        result = await manager.exists("existing-key")
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        mock_client.exists.return_value = 0
        result = await manager.exists("missing-key")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_before_connect(self, manager: RedisManager) -> None:
        result = await manager.exists("key")
        assert result is False


# ===========================================================================
# Additional utilities
# ===========================================================================


@pytest.mark.unit
class TestTtl:
    """Tests for ``RedisManager.ttl``."""

    @pytest.mark.asyncio
    async def test_ttl(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        result = await manager.ttl("key")
        assert result == 300
        mock_client.ttl.assert_awaited_once_with("key")

    @pytest.mark.asyncio
    async def test_ttl_before_connect(self, manager: RedisManager) -> None:
        result = await manager.ttl("key")
        assert result == -2


@pytest.mark.unit
class TestExpire:
    """Tests for ``RedisManager.expire``."""

    @pytest.mark.asyncio
    async def test_expire(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        result = await manager.expire("key", 600)
        assert result is True
        mock_client.expire.assert_awaited_once_with("key", 600)

    @pytest.mark.asyncio
    async def test_expire_before_connect(self, manager: RedisManager) -> None:
        result = await manager.expire("key", 600)
        assert result is False


@pytest.mark.unit
class TestKeys:
    """Tests for ``RedisManager.keys``."""

    @pytest.mark.asyncio
    async def test_keys(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        result = await manager.keys("trade:*")
        assert result == ["key1", "key2"]
        mock_client.keys.assert_awaited_once_with("trade:*")

    @pytest.mark.asyncio
    async def test_keys_before_connect(self, manager: RedisManager) -> None:
        result = await manager.keys("*")
        assert result == []


# ===========================================================================
# Health check
# ===========================================================================


@pytest.mark.unit
class TestHealthCheck:
    """Tests for ``RedisManager.health_check``."""

    @pytest.mark.asyncio
    async def test_healthy(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        result = await manager.health_check()
        assert result["status"] == "healthy"
        assert result["latency_ms"] is not None
        assert result["error"] is None
        assert result["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_unhealthy_not_connected(self, manager: RedisManager) -> None:
        result = await manager.health_check()
        assert result["status"] == "unhealthy"
        assert result["error"] == "not connected"
        assert result["latency_ms"] is None

    @pytest.mark.asyncio
    async def test_unhealthy_ping_fails(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        mock_client.ping = AsyncMock(side_effect=ConnectionError("Redis down"))

        result = await manager.health_check()
        assert result["status"] == "unhealthy"
        assert result["error"] == "Redis down"
        assert result["latency_ms"] is not None

    @pytest.mark.asyncio
    async def test_degraded_ping_returns_false(self, manager: RedisManager, mock_client: MagicMock) -> None:
        manager.client = mock_client
        mock_client.ping = AsyncMock(return_value=False)

        result = await manager.health_check()
        assert result["status"] == "degraded"


# ===========================================================================
# Context manager
# ===========================================================================


@pytest.mark.unit
class TestAsyncContextManager:
    """Tests for ``RedisManager`` as an async context manager."""

    @pytest.mark.asyncio
    async def test_aenter_connects(self, manager: RedisManager) -> None:
        with patch.object(manager, "connect", new_callable=AsyncMock) as mock_connect:
            async with manager as mgr:
                assert mgr is manager
            mock_connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aexit_closes(self, manager: RedisManager) -> None:
        with patch.object(manager, "connect", new_callable=AsyncMock):
            with patch.object(manager, "close", new_callable=AsyncMock) as mock_close:
                async with manager:
                    pass
                mock_close.assert_awaited_once()
