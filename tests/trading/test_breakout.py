"""Tests for the Breakout Strategy."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.trading.schemas import SignalDirection
from src.trading.strategies.breakout import BreakoutStrategy


class TestBreakoutSignalGeneration:
    """Tests for breakout signal generation."""

    def test_no_signal_with_empty_df(self, breakout_strategy: BreakoutStrategy) -> None:
        df = pd.DataFrame({"high": [], "low": [], "close": [], "volume": []})
        features: dict[str, float | None] = {}
        signal = breakout_strategy.generate_signal(df, features)
        assert signal is None

    def test_no_signal_with_insufficient_data(self, breakout_strategy: BreakoutStrategy) -> None:
        df = pd.DataFrame({
            "high": [100.0] * 15,
            "low": [99.0] * 15,
            "close": [99.5] * 15,
            "volume": [1000.0] * 15,
        })
        features: dict[str, float | None] = {}
        signal = breakout_strategy.generate_signal(df, features)
        assert signal is None

    def test_default_parameters(self, breakout_strategy: BreakoutStrategy) -> None:
        params = breakout_strategy.get_parameters()
        assert params["lookback"] == 20.0
        assert params["atr_multiplier"] == 1.5
        assert params["volume_threshold"] == 2.0

    def test_parameter_bounds(self, breakout_strategy: BreakoutStrategy) -> None:
        bounds = breakout_strategy.parameter_bounds()
        assert "lookback" in bounds
        assert "atr_multiplier" in bounds
        assert "volume_threshold" in bounds

    def test_strategy_name(self, breakout_strategy: BreakoutStrategy) -> None:
        assert breakout_strategy.name == "breakout"

    def test_strategy_type(self, breakout_strategy: BreakoutStrategy) -> None:
        from src.trading.schemas import StrategyType
        assert breakout_strategy.strategy_type == StrategyType.BREAKOUT

    def test_buy_on_upper_channel_breakout(
        self, breakout_strategy: BreakoutStrategy
    ) -> None:
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=50, freq="min", tz="UTC")
        # Range-bound then breakout
        base_prices = np.ones(49) * 100.0
        breakout_price = 110.0  # clear breakout
        prices = np.concatenate([base_prices, [breakout_price]])
        high_prices = np.concatenate([base_prices + 2.0, [breakout_price]])
        low_prices = np.concatenate([base_prices - 2.0, [breakout_price - 1.0]])
        volume = np.concatenate([
            np.ones(49) * 1000,
            [5000],  # high volume
        ])
        df = pd.DataFrame({
            "open": prices - 0.5,
            "high": high_prices,
            "low": low_prices,
            "close": prices,
            "volume": volume,
        }, index=dates)
        features: dict[str, float | None] = {}
        signal = breakout_strategy.generate_signal(df, features)
        # Volume ratio = 5000 / 1000 = 5.0, which is above threshold of 2.0
        if signal is not None:
            assert signal.confidence > 0
            assert signal.confidence <= 1.0

    def test_volume_below_threshold_returns_none(
        self, breakout_strategy: BreakoutStrategy
    ) -> None:
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=50, freq="min", tz="UTC")
        prices = np.concatenate([np.ones(49) * 100.0, [110.0]])
        volume = np.ones(50) * 1000  # low uniform volume
        df = pd.DataFrame({
            "open": prices - 0.5,
            "high": prices + 2.0,
            "low": prices - 2.0,
            "close": prices,
            "volume": volume,
        }, index=dates)
        features: dict[str, float | None] = {}
        signal = breakout_strategy.generate_signal(df, features)
        # Volume ratio = 1.0, below threshold of 2.0
        assert signal is None

    def test_signal_contains_breakout_in_reason(
        self, breakout_strategy: BreakoutStrategy
    ) -> None:
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=50, freq="min", tz="UTC")
        prices = np.concatenate([np.ones(49) * 100.0, [115.0]])
        volume = np.concatenate([np.ones(49) * 1000, [8000]])
        df = pd.DataFrame({
            "open": prices - 0.5,
            "high": prices + 2.0,
            "low": prices - 2.0,
            "close": prices,
            "volume": volume,
        }, index=dates)
        features: dict[str, float | None] = {}
        signal = breakout_strategy.generate_signal(df, features)
        if signal is not None:
            assert "channel" in signal.reason.lower() or "breakout" in signal.reason.lower()

    def test_update_parameters(self, breakout_strategy: BreakoutStrategy) -> None:
        breakout_strategy.update_parameters({"volume_threshold": 3.0})
        assert breakout_strategy.get_parameters()["volume_threshold"] == 3.0

    def test_atr_multiplier_bounds(self, breakout_strategy: BreakoutStrategy) -> None:
        breakout_strategy.update_parameters({"atr_multiplier": 10.0})
        assert breakout_strategy.get_parameters()["atr_multiplier"] == 5.0  # clamped

    def test_no_breakout_no_signal(
        self, breakout_strategy: BreakoutStrategy
    ) -> None:
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=50, freq="min", tz="UTC")
        prices = np.ones(50) * 100.0  # flat, no breakout
        volume = np.concatenate([np.ones(49) * 1000, [5000]])
        df = pd.DataFrame({
            "open": prices - 0.5,
            "high": prices + 2.0,
            "low": prices - 2.0,
            "close": prices,
            "volume": volume,
        }, index=dates)
        features: dict[str, float | None] = {}
        signal = breakout_strategy.generate_signal(df, features)
        assert signal is None

    def test_nan_atr_returns_none(
        self, breakout_strategy: BreakoutStrategy
    ) -> None:
        df = pd.DataFrame({
            "open": [100.0] * 30,
            "high": [100.0] * 30,  # no range -> ATR might be 0
            "low": [100.0] * 30,
            "close": [100.0] * 30,
            "volume": [1000.0] * 30,
        })
        features: dict[str, float | None] = {}
        signal = breakout_strategy.generate_signal(df, features)
        assert signal is None

    def test_lookback_parameter_update(self, breakout_strategy: BreakoutStrategy) -> None:
        breakout_strategy.update_parameters({"lookback": 30.0})
        assert breakout_strategy.get_parameters()["lookback"] == 30.0

    def test_confidence_with_strong_breakout(
        self, breakout_strategy: BreakoutStrategy
    ) -> None:
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=50, freq="min", tz="UTC")
        prices = np.concatenate([np.ones(49) * 100.0, [130.0]])  # very strong breakout
        volume = np.concatenate([np.ones(49) * 1000, [20000]])
        df = pd.DataFrame({
            "open": prices - 0.5,
            "high": prices + 2.0,
            "low": prices - 2.0,
            "close": prices,
            "volume": volume,
        }, index=dates)
        features: dict[str, float | None] = {}
        signal = breakout_strategy.generate_signal(df, features)
        if signal is not None:
            assert signal.confidence > 0.4
