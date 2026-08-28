"""Tests for the abstract BaseStrategy class."""

from __future__ import annotations

import pickle
from datetime import datetime, timezone

import pandas as pd
import pytest

from src.trading.base_strategy import BaseStrategy, _unpickle_strategy
from src.trading.schemas import (
    SignalDirection,
    StrategyConfig,
    StrategySignal,
    StrategyType,
)
from tests.trading.conftest import MockStrategy


class TestBaseStrategyLifecycle:
    """Tests for strategy lifecycle (init, teardown, health)."""

    @pytest.mark.asyncio
    async def test_initialize(self, mock_strategy: MockStrategy) -> None:
        assert mock_strategy._initialized is False
        await mock_strategy.initialize()
        assert mock_strategy._initialized is True

    @pytest.mark.asyncio
    async def test_teardown(self, mock_strategy: MockStrategy) -> None:
        await mock_strategy.initialize()
        assert mock_strategy._initialized is True
        await mock_strategy.teardown()
        assert mock_strategy._initialized is False

    @pytest.mark.asyncio
    async def test_health(self, mock_strategy: MockStrategy) -> None:
        await mock_strategy.initialize()
        health = await mock_strategy.health()
        assert health["name"] == "mock_strategy"
        assert health["strategy_type"] == "trend_following"
        assert health["initialized"] is True
        assert health["enabled"] is True

    def test_name_attribute(self, mock_strategy: MockStrategy) -> None:
        assert mock_strategy.name == "mock_strategy"

    def test_strategy_type_attribute(self, mock_strategy: MockStrategy) -> None:
        assert mock_strategy.strategy_type == StrategyType.TREND_FOLLOWING


class TestBaseStrategyParameters:
    """Tests for parameter management."""

    def test_default_parameters(self, mock_strategy: MockStrategy) -> None:
        params = mock_strategy.get_parameters()
        assert "threshold" in params
        assert params["threshold"] == 60.0

    def test_parameter_bounds(self, mock_strategy: MockStrategy) -> None:
        bounds = mock_strategy.parameter_bounds()
        assert "threshold" in bounds
        assert bounds["threshold"] == (0.0, 100.0)

    def test_update_parameters(self, mock_strategy: MockStrategy) -> None:
        mock_strategy.update_parameters({"threshold": 75.0})
        assert mock_strategy.get_parameters()["threshold"] == 75.0

    def test_update_parameters_clamped(self, mock_strategy: MockStrategy) -> None:
        mock_strategy.update_parameters({"threshold": 150.0})
        assert mock_strategy.get_parameters()["threshold"] == 100.0  # clamped to max

    def test_update_parameters_clamped_min(self, mock_strategy: MockStrategy) -> None:
        mock_strategy.update_parameters({"threshold": -10.0})
        assert mock_strategy.get_parameters()["threshold"] == 0.0  # clamped to min

    def test_update_unknown_parameter_raises(self, mock_strategy: MockStrategy) -> None:
        with pytest.raises(ValueError, match="Unknown parameter"):
            mock_strategy.update_parameters({"unknown_param": 50.0})

    def test_update_syncs_config(self, mock_strategy: MockStrategy) -> None:
        mock_strategy.update_parameters({"threshold": 80.0})
        assert mock_strategy.config.parameters["threshold"] == 80.0

    def test_validate_parameters_valid(self, mock_strategy: MockStrategy) -> None:
        mock_strategy._validate_parameters({"threshold": 50.0})

    def test_validate_parameters_out_of_bounds(self, mock_strategy: MockStrategy) -> None:
        with pytest.raises(ValueError, match="out of bounds"):
            mock_strategy._validate_parameters({"threshold": 150.0})


class TestBaseStrategySignalGeneration:
    """Tests for signal generation via MockStrategy."""

    def test_generate_buy_signal(self, mock_strategy: MockStrategy, sample_features: dict) -> None:
        features = dict(sample_features)
        features["rsi_14"] = 70.0  # Above threshold of 60
        signal = mock_strategy.generate_signal(pd.DataFrame(), features)
        assert signal is not None
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence == 0.7

    def test_generate_sell_signal(self, mock_strategy: MockStrategy, sample_features: dict) -> None:
        features = dict(sample_features)
        features["rsi_14"] = 30.0  # Below threshold of 40 (100-60)
        signal = mock_strategy.generate_signal(pd.DataFrame(), features)
        assert signal is not None
        assert signal.direction == SignalDirection.SELL

    def test_no_signal_when_rsi_mid(self, mock_strategy: MockStrategy, sample_features: dict) -> None:
        features = dict(sample_features)
        features["rsi_14"] = 50.0  # In the middle, no signal
        signal = mock_strategy.generate_signal(pd.DataFrame(), features)
        assert signal is None

    def test_no_signal_missing_feature(self, mock_strategy: MockStrategy) -> None:
        features: dict[str, float | None] = {"rsi_14": None}
        signal = mock_strategy.generate_signal(pd.DataFrame(), features)
        assert signal is None

    def test_signal_includes_strategy_name(self, mock_strategy: MockStrategy, sample_features: dict) -> None:
        features = dict(sample_features)
        features["rsi_14"] = 70.0
        signal = mock_strategy.generate_signal(pd.DataFrame(), features)
        assert signal is not None
        assert signal.strategy_name == "mock_strategy"
        assert signal.symbol == "SOL/USDC"

    def test_signal_includes_parameters(self, mock_strategy: MockStrategy, sample_features: dict) -> None:
        features = dict(sample_features)
        features["rsi_14"] = 70.0
        signal = mock_strategy.generate_signal(pd.DataFrame(), features)
        assert signal is not None
        assert "threshold" in signal.parameters_used

    def test_signal_includes_features_used(self, mock_strategy: MockStrategy, sample_features: dict) -> None:
        features = dict(sample_features)
        features["rsi_14"] = 70.0
        signal = mock_strategy.generate_signal(pd.DataFrame(), features)
        assert signal is not None
        assert len(signal.features_used) > 0


class TestBaseStrategyState:
    """Tests for state persistence."""

    def test_get_state(self, mock_strategy: MockStrategy) -> None:
        state = mock_strategy.get_state()
        assert state["name"] == "mock_strategy"
        assert state["parameters"]["threshold"] == 60.0
        assert state["enabled"] is True

    def test_set_state(self, mock_strategy: MockStrategy) -> None:
        new_state = {
            "name": "mock_strategy",
            "strategy_type": "trend_following",
            "parameters": {"threshold": 80.0},
            "enabled": False,
            "state_data": {"test_key": "test_value"},
            "last_signal_time": None,
        }
        mock_strategy.set_state(new_state)
        assert mock_strategy.get_parameters()["threshold"] == 80.0
        assert mock_strategy._enabled is False
        assert mock_strategy._state_data["test_key"] == "test_value"

    def test_to_strategy_state(self, mock_strategy: MockStrategy) -> None:
        strategy_state = mock_strategy.to_strategy_state()
        assert strategy_state.name == "mock_strategy"
        assert strategy_state.parameters["threshold"] == 60.0


class TestBaseStrategyPickle:
    """Tests for pickle serialization (hot-swap support)."""

    def test_pickle_roundtrip(self, mock_strategy: MockStrategy) -> None:
        pickled = pickle.dumps(mock_strategy)
        restored = pickle.loads(pickled)
        assert restored.name == "mock_strategy"
        assert restored.get_parameters()["threshold"] == 60.0

    def test_pickle_preserves_parameters(self, mock_strategy: MockStrategy) -> None:
        mock_strategy.update_parameters({"threshold": 85.0})
        pickled = pickle.dumps(mock_strategy)
        restored = pickle.loads(pickled)
        assert restored.get_parameters()["threshold"] == 85.0

    def test_pickle_preserves_state(self, mock_strategy: MockStrategy) -> None:
        mock_strategy._state_data = {"counter": 5}
        pickled = pickle.dumps(mock_strategy)
        restored = pickle.loads(pickled)
        assert restored._state_data["counter"] == 5

    def test_unpickle_strategy_helper(self) -> None:
        state = {
            "name": "test_strategy",
            "strategy_type": "trend_following",
            "config": {
                "strategy_type": "trend_following",
                "symbol": "SOL/USDC",
                "parameters": {},
                "enabled": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            "parameters": {},
            "enabled": True,
            "state_data": {},
            "last_signal_time": None,
        }
        strategy = _unpickle_strategy(state)
        assert strategy.name == "test_strategy"


class TestBaseStrategyHelpers:
    """Tests for helper methods."""

    def test_safe_feature_present(self, mock_strategy: MockStrategy) -> None:
        features = {"rsi_14": 65.0}
        assert BaseStrategy._safe_feature(features, "rsi_14") == 65.0

    def test_safe_feature_missing(self, mock_strategy: MockStrategy) -> None:
        features: dict[str, float | None] = {}
        assert BaseStrategy._safe_feature(features, "rsi_14") is None

    def test_safe_feature_nan(self, mock_strategy: MockStrategy) -> None:
        import math
        features: dict[str, float | None] = {"rsi_14": float("nan")}
        result = BaseStrategy._safe_feature(features, "rsi_14")
        assert result is None

    def test_safe_feature_none_value(self, mock_strategy: MockStrategy) -> None:
        features: dict[str, float | None] = {"rsi_14": None}
        assert BaseStrategy._safe_feature(features, "rsi_14") is None

    def test_clamp_confidence_low(self) -> None:
        assert BaseStrategy._clamp_confidence(-0.5) == 0.0

    def test_clamp_confidence_high(self) -> None:
        assert BaseStrategy._clamp_confidence(1.5) == 1.0

    def test_clamp_confidence_mid(self) -> None:
        assert BaseStrategy._clamp_confidence(0.5) == 0.5


class TestBaseStrategyConfig:
    """Tests for config handling."""

    def test_config_symbol(self, mock_strategy: MockStrategy) -> None:
        assert mock_strategy.config.symbol == "SOL/USDC"

    def test_default_config(self) -> None:
        strategy = MockStrategy()
        assert strategy.config.symbol == "UNKNOWN"

    def test_custom_config(self) -> None:
        config = StrategyConfig(
            strategy_type=StrategyType.MOMENTUM,
            symbol="BTC/USDC",
            parameters={"threshold": 70.0},
        )
        strategy = MockStrategy(config)
        assert strategy.config.symbol == "BTC/USDC"
        assert strategy.parameters["threshold"] == 70.0


class TestBaseStrategyEnabled:
    """Tests for enabled/disabled state."""

    def test_default_enabled(self, mock_strategy: MockStrategy) -> None:
        assert mock_strategy._enabled is True

    def test_set_enabled(self, mock_strategy: MockStrategy) -> None:
        mock_strategy._enabled = False
        assert mock_strategy._enabled is False
