"""Tests for the FeatureStore (online Redis + offline TimescaleDB)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from src.data.feature_store import FeatureStore
from src.data.models import FeatureRecord


class TestFeatureStoreOnline:
    @pytest.mark.asyncio
    async def test_get_online_existing(self, feature_store, mock_redis_manager):
        mock_redis_manager.get = AsyncMock(return_value={"value": 65.4})
        result = await feature_store.get_online("SOL/USDC", "rsi_14")
        assert result == 65.4

    @pytest.mark.asyncio
    async def test_get_online_missing(self, feature_store, mock_redis_manager):
        mock_redis_manager.get = AsyncMock(return_value=None)
        result = await feature_store.get_online("SOL/USDC", "rsi_14")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_online_raw_number(self, feature_store, mock_redis_manager):
        mock_redis_manager.get = AsyncMock(return_value=42.0)
        result = await feature_store.get_online("SOL/USDC", "test")
        assert result == 42.0

    @pytest.mark.asyncio
    async def test_get_online_raw_string(self, feature_store, mock_redis_manager):
        mock_redis_manager.get = AsyncMock(return_value="99.9")
        result = await feature_store.get_online("SOL/USDC", "test")
        assert result == 99.9

    @pytest.mark.asyncio
    async def test_get_online_parse_error(self, feature_store, mock_redis_manager):
        mock_redis_manager.get = AsyncMock(return_value="not_a_number")
        result = await feature_store.get_online("SOL/USDC", "test")
        assert result is None

    @pytest.mark.asyncio
    async def test_write_online(self, feature_store, mock_redis_manager):
        result = await feature_store.write_online("SOL/USDC", "rsi_14", 65.4, ttl=300)
        assert result is True
        mock_redis_manager.set.assert_called_once()
        call_args = mock_redis_manager.set.call_args
        assert "feature:SOL/USDC:rsi_14" in str(call_args)

    @pytest.mark.asyncio
    async def test_write_online_false(self, feature_store, mock_redis_manager):
        mock_redis_manager.set = AsyncMock(return_value=False)
        result = await feature_store.write_online("SOL/USDC", "rsi_14", 65.4)
        assert result is False

    @pytest.mark.asyncio
    async def test_batch_write_online(self, feature_store, mock_redis_manager):
        features = {"rsi_14": 65.4, "ema_9": 142.3}
        result = await feature_store.batch_write_online("SOL/USDC", features)
        assert result == {"rsi_14": True, "ema_9": True}
        assert mock_redis_manager.set.call_count == 2


class TestFeatureStoreOffline:
    @pytest.mark.asyncio
    async def test_write_offline(self, feature_store, mock_db_manager):
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_db_manager.get_session = MagicMock(return_value=mock_cm)

        features = {"rsi_14": 65.4, "ema_9": 142.3}
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        await feature_store.write_offline("SOL/USDC", features, ts)
        assert mock_session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_write_offline_no_timestamp(self, feature_store, mock_db_manager):
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_db_manager.get_session = MagicMock(return_value=mock_cm)

        features = {"rsi_14": 65.4}
        await feature_store.write_offline("SOL/USDC", features)
        assert mock_session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_get_offline(self, feature_store, mock_db_manager):
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        record = FeatureRecord(
            symbol="SOL/USDC",
            timestamp=ts,
            feature_name="rsi_14",
            feature_value={"value": 65.4},
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [record]

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_db_manager.get_session = MagicMock(return_value=mock_cm)

        rows = await feature_store.get_offline("SOL/USDC", "rsi_14", ts, ts)
        assert len(rows) == 1
        assert rows[0]["feature_value"] == {"value": 65.4}

    @pytest.mark.asyncio
    async def test_batch_write_offline(self, feature_store, mock_db_manager):
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_db_manager.get_session = MagicMock(return_value=mock_cm)

        features_dict = {
            "2024-01-01T00:00:00+00:00": {"rsi_14": 65.4},
            "2024-01-01T00:01:00+00:00": {"rsi_14": 62.1},
        }
        await feature_store.batch_write_offline("SOL/USDC", features_dict)
        assert mock_session.add.call_count == 2


class TestFeatureStoreKeyFormat:
    def test_online_key_format(self, feature_store):
        key = feature_store._online_key("SOL/USDC", "rsi_14")
        assert key == "feature:SOL/USDC:rsi_14"

    def test_online_key_prefix_custom(self, mock_db_manager, mock_redis_manager):
        store = FeatureStore(mock_db_manager, mock_redis_manager, key_prefix="myprefix")
        key = store._online_key("BTC", "sma_20")
        assert key == "myprefix:BTC:sma_20"
