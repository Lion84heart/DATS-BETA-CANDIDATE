"""Shared pytest fixtures for data platform tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

from src.data.feature_store import FeatureStore
from src.data.features import FeatureEngine
from src.data.models import Base, DataQualityLog, FeatureRecord
from src.data.quality import DataQualityEngine, DataQualityReport
from src.data.streaming import DataStreamPipeline


# ---------------------------------------------------------------------------
# Mock infrastructure fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db_manager():
    """Return a mock DatabaseManager."""
    mgr = MagicMock()
    mgr.get_session = MagicMock()
    return mgr


@pytest.fixture
def mock_redis_manager():
    """Return a mock RedisManager with async get/set."""
    mgr = MagicMock()
    mgr.get = AsyncMock(return_value=None)
    mgr.set = AsyncMock(return_value=True)
    mgr.delete = AsyncMock(return_value=1)
    mgr.keys = AsyncMock(return_value=[])
    return mgr


@pytest.fixture
def mock_kafka_producer():
    """Return a mock KafkaProducer."""
    producer = MagicMock()
    producer.send = AsyncMock(return_value={"topic": "test", "partition": 0, "offset": 1})
    return producer


@pytest.fixture
def mock_kafka_consumer():
    """Return a mock KafkaConsumer."""
    consumer = MagicMock()
    consumer.consume = AsyncMock(return_value=MagicMock())
    return consumer


# ---------------------------------------------------------------------------
# Component fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def feature_store(mock_db_manager, mock_redis_manager) -> FeatureStore:
    return FeatureStore(mock_db_manager, mock_redis_manager)


@pytest.fixture
def feature_engine() -> FeatureEngine:
    return FeatureEngine()


@pytest.fixture
def quality_engine() -> DataQualityEngine:
    return DataQualityEngine()


@pytest.fixture
def data_stream_pipeline(mock_kafka_producer, mock_kafka_consumer) -> DataStreamPipeline:
    return DataStreamPipeline(mock_kafka_producer, mock_kafka_consumer)


# ---------------------------------------------------------------------------
# DataFrame fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ohlcv_df() -> pd.DataFrame:
    """Return a realistic OHLCV DataFrame with 200 rows."""
    np.random.seed(42)
    n = 200
    base = 100.0
    prices = [base]
    for _ in range(n - 1):
        prices.append(prices[-1] * (1 + np.random.normal(0, 0.01)))

    df = pd.DataFrame({
        "open": prices,
        "high": [p * (1 + abs(np.random.normal(0, 0.005))) for p in prices],
        "low": [p * (1 - abs(np.random.normal(0, 0.005))) for p in prices],
        "close": [p * (1 + np.random.normal(0, 0.002)) for p in prices],
        "volume": np.random.uniform(1000, 10000, n),
    })
    # Ensure high >= low
    df["high"] = np.maximum(df["high"], df["low"] * 1.001)
    df.index = pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC")
    return df


@pytest.fixture
def small_ohlcv_df() -> pd.DataFrame:
    """Return a small OHLCV DataFrame with 10 rows."""
    np.random.seed(42)
    n = 10
    base = 100.0
    prices = [base]
    for _ in range(n - 1):
        prices.append(prices[-1] * (1 + np.random.normal(0, 0.01)))

    df = pd.DataFrame({
        "open": prices,
        "high": [p * (1 + abs(np.random.normal(0, 0.005))) for p in prices],
        "low": [p * (1 - abs(np.random.normal(0, 0.005))) for p in prices],
        "close": [p * (1 + np.random.normal(0, 0.002)) for p in prices],
        "volume": np.random.uniform(1000, 10000, n),
    })
    df["high"] = np.maximum(df["high"], df["low"] * 1.001)
    df.index = pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC")
    return df


@pytest.fixture
def empty_df() -> pd.DataFrame:
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Model fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_feature_record():
    return FeatureRecord(
        symbol="SOL/USDC",
        timestamp=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        feature_name="rsi_14",
        feature_value={"value": 65.4},
    )


@pytest.fixture
def sample_quality_log():
    return DataQualityLog(
        timestamp=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        source="jupiter",
        check_type="freshness",
        status="passed",
        details={"max_age": 60},
    )
