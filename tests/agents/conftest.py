"""Shared pytest fixtures for agent framework tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Mock Redis
# ---------------------------------------------------------------------------


class MockRedisClient:
    """In-memory mock for redis.asyncio.Redis."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._ttls: dict[str, int] = {}

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> Any:
        return self._store.get(key)

    async def set(
        self,
        key: str,
        value: Any,
        ex: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        if nx and key in self._store:
            return False
        if xx and key not in self._store:
            return False
        self._store[key] = value
        if ex is not None:
            self._ttls[key] = ex
        return True

    async def delete(self, key: str) -> int:
        if key in self._store:
            del self._store[key]
            self._ttls.pop(key, None)
            return 1
        return 0

    async def exists(self, key: str) -> int:
        return 1 if key in self._store else 0

    async def ttl(self, key: str) -> int:
        return self._ttls.get(key, -1) if key in self._store else -2

    async def expire(self, key: str, seconds: int) -> bool:
        if key in self._store:
            self._ttls[key] = seconds
            return True
        return False

    async def keys(self, pattern: str = "*") -> list[str]:
        import fnmatch
        return [k for k in self._store if fnmatch.fnmatch(k, pattern)]

    async def lpush(self, key: str, *values: Any) -> int:
        if key not in self._store:
            self._store[key] = []
        for v in reversed(values):
            self._store[key].insert(0, v)
        return len(self._store[key])

    async def lrange(self, key: str, start: int, end: int) -> list[Any]:
        lst = self._store.get(key, [])
        if end < 0:
            end = len(lst)
        return lst[start:end + 1]

    async def close(self) -> None:
        pass

    def clear(self) -> None:
        self._store.clear()
        self._ttls.clear()


@pytest.fixture
def mock_redis_client() -> MockRedisClient:
    """Provide a fresh mock Redis client."""
    return MockRedisClient()


@pytest.fixture
def mock_redis_manager(mock_redis_client: MockRedisClient) -> MagicMock:
    """Provide a mock RedisManager with in-memory backing."""
    manager = MagicMock()
    manager.client = mock_redis_client

    async def _get(key: str) -> Any | None:
        raw = await mock_redis_client.get(key)
        if raw is None:
            return None
        import json
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return raw

    async def _set(key: str, value: Any, *, ttl: int | None = 3600, nx: bool = False, xx: bool = False) -> bool:
        import json
        payload = json.dumps(value, default=str) if not isinstance(value, str) else value
        return await mock_redis_client.set(key, payload, ex=ttl, nx=nx, xx=xx)

    async def _delete(key: str) -> int:
        return await mock_redis_client.delete(key)

    async def _exists(key: str) -> bool:
        return (await mock_redis_client.exists(key)) > 0

    async def _ttl(key: str) -> int:
        return await mock_redis_client.ttl(key)

    async def _expire(key: str, seconds: int) -> bool:
        return await mock_redis_client.expire(key, seconds)

    async def _keys(pattern: str = "*") -> list[str]:
        return await mock_redis_client.keys(pattern)

    manager.get = _get
    manager.set = _set
    manager.delete = _delete
    manager.exists = _exists
    manager.ttl = _ttl
    manager.expire = _expire
    manager.keys = _keys
    manager.connect = AsyncMock(return_value=mock_redis_client)
    manager.close = AsyncMock()

    return manager


# ---------------------------------------------------------------------------
# Mock Kafka
# ---------------------------------------------------------------------------


class MockKafkaProducer:
    """In-memory mock for KafkaProducer."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self._started: bool = False

    async def start(self) -> Any:
        self._started = True
        return self

    async def stop(self) -> None:
        self._started = False

    async def send(self, topic: str, value: Any, *, key: str | None = None, headers: Any = None) -> dict[str, Any]:
        msg = {"topic": topic, "value": value, "key": key, "partition": 0, "offset": len(self.messages)}
        self.messages.append(msg)
        return {"topic": topic, "partition": 0, "offset": len(self.messages) - 1}

    async def health_check(self) -> dict[str, Any]:
        return {"status": "healthy", "partitions": 1, "error": None}

    async def __aenter__(self) -> MockKafkaProducer:
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.stop()


@pytest.fixture
def mock_kafka_producer() -> MockKafkaProducer:
    """Provide a fresh mock Kafka producer."""
    return MockKafkaProducer()


# ---------------------------------------------------------------------------
# Mock FeatureStore
# ---------------------------------------------------------------------------


class MockFeatureStore:
    """In-memory mock for FeatureStore."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, float]] = {}

    def set_features(self, symbol: str, features: dict[str, float]) -> None:
        if symbol not in self._data:
            self._data[symbol] = {}
        self._data[symbol].update(features)

    async def get_online(self, symbol: str, feature: str) -> float | None:
        return self._data.get(symbol, {}).get(feature)

    async def write_online(self, symbol: str, feature: str, value: float, ttl: int = 300) -> bool:
        if symbol not in self._data:
            self._data[symbol] = {}
        self._data[symbol][feature] = value
        return True

    async def batch_write_online(self, symbol: str, features: dict[str, float], ttl: int = 300) -> dict[str, bool]:
        results = {}
        for feat, val in features.items():
            results[feat] = await self.write_online(symbol, feat, val, ttl)
        return results

    async def get_offline(self, symbol: str, feature: str, start: datetime, end: datetime, limit: int = 10000) -> list[dict[str, Any]]:
        return []


@pytest.fixture
def mock_feature_store() -> MockFeatureStore:
    """Provide a fresh mock FeatureStore."""
    return MockFeatureStore()


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_features() -> dict[str, float]:
    """Bullish feature set for testing."""
    return {
        "rsi_14": 55.0,
        "macd": 0.5,
        "macd_signal": 0.2,
        "macd_histogram": 0.3,
        "bb_upper": 110.0,
        "bb_lower": 90.0,
        "bb_pct_b": 0.55,
        "ema_9": 102.0,
        "ema_21": 100.0,
        "ema_50": 98.0,
        "sma_20": 101.0,
        "sma_50": 99.0,
        "atr_14": 2.5,
        "adx_14": 28.0,
        "plus_di": 25.0,
        "minus_di": 15.0,
        "relative_volume": 1.2,
        "return_1m": 0.005,
        "z_score": 0.8,
        "close": 105.0,
        "dist_from_ema50": 0.071,
    }


@pytest.fixture
def sample_bearish_features() -> dict[str, float]:
    """Bearish feature set for testing."""
    return {
        "rsi_14": 75.0,
        "macd": -0.3,
        "macd_signal": 0.1,
        "macd_histogram": -0.4,
        "bb_upper": 110.0,
        "bb_lower": 90.0,
        "bb_pct_b": 0.92,
        "ema_9": 95.0,
        "ema_21": 98.0,
        "ema_50": 100.0,
        "sma_20": 96.0,
        "sma_50": 99.0,
        "atr_14": 3.0,
        "adx_14": 30.0,
        "plus_di": 12.0,
        "minus_di": 28.0,
        "relative_volume": 1.5,
        "return_1m": -0.008,
        "z_score": -1.5,
        "close": 92.0,
        "dist_from_ema50": -0.08,
    }


@pytest.fixture
def sample_signal_data() -> dict[str, Any]:
    """Sample signal dict for testing."""
    return {
        "symbol": "SOL/USDC",
        "direction": "BUY",
        "confidence": 0.75,
        "reason": "Bullish trend detected",
        "features_used": {"rsi_14": 55.0, "macd": 0.5},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": "strat-1",
        "strategy": "trend_following",
    }


@pytest.fixture
def sample_agent_health() -> dict[str, Any]:
    """Sample agent health dict for testing."""
    return {
        "agent_id": "test-agent",
        "state": "idle",
        "last_active": datetime.now(timezone.utc).isoformat(),
        "error_count": 0,
        "tasks_completed": 5,
        "metadata": {"agent_type": "test"},
    }
