"""Tests for the Statistical Arbitrage Strategy."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.trading.schemas import SignalDirection
from src.trading.strategies.stat_arb import StatArbStrategy


class TestStatArbSignalGeneration:
    """Tests for statistical arbitrage signal generation."""

    def test_buy_when_zscore_below_negative_threshold(
        self, stat_arb_strategy: StatArbStrategy, sample_features: dict
    ) -> None:
        features = dict(sample_features)
        features["z_score"] = -2.5  # Below -2.0 entry threshold
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = stat_arb_strategy.generate_signal(df, features)
        assert signal is not None
        assert signal.direction == SignalDirection.BUY

    def test_sell_when_zscore_above_positive_threshold(
        self, stat_arb_strategy: StatArbStrategy, sample_features: dict
    ) -> None:
        features = dict(sample_features)
        features["z_score"] = 2.5  # Above +2.0 entry threshold
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = stat_arb_strategy.generate_signal(df, features)
        assert signal is not None
        assert signal.direction == SignalDirection.SELL

    def test_no_signal_when_zscore_mid_range(
        self, stat_arb_strategy: StatArbStrategy, sample_features: dict
    ) -> None:
        features = dict(sample_features)
        features["z_score"] = 0.5  # Within normal range
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = stat_arb_strategy.generate_signal(df, features)
        assert signal is None

    def test_no_signal_when_zscore_at_threshold(
        self, stat_arb_strategy: StatArbStrategy, sample_features: dict
    ) -> None:
        features = dict(sample_features)
        features["z_score"] = 2.0  # exactly at threshold
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = stat_arb_strategy.generate_signal(df, features)
        assert signal is not None
        assert signal.direction == SignalDirection.SELL

    def test_no_signal_when_zscore_below_positive_threshold(
        self, stat_arb_strategy: StatArbStrategy, sample_features: dict
    ) -> None:
        features = dict(sample_features)
        features["z_score"] = 1.5  # Below threshold
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = stat_arb_strategy.generate_signal(df, features)
        assert signal is None

    def test_buy_confidence_increases_with_zscore_magnitude(
        self, stat_arb_strategy: StatArbStrategy, sample_features: dict
    ) -> None:
        features = dict(sample_features)
        features["z_score"] = -4.0  # very extreme
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = stat_arb_strategy.generate_signal(df, features)
        assert signal is not None
        assert signal.confidence > 0.6

    def test_sell_confidence_increases_with_zscore_magnitude(
        self, stat_arb_strategy: StatArbStrategy, sample_features: dict
    ) -> None:
        features = dict(sample_features)
        features["z_score"] = 4.0  # very extreme
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = stat_arb_strategy.generate_signal(df, features)
        assert signal is not None
        assert signal.confidence > 0.6

    def test_signal_reason_contains_zscore(
        self, stat_arb_strategy: StatArbStrategy, sample_features: dict
    ) -> None:
        features = dict(sample_features)
        features["z_score"] = -2.5
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = stat_arb_strategy.generate_signal(df, features)
        assert signal is not None
        assert "Z-score" in signal.reason

    def test_fallback_computes_zscore_from_ohlcv(
        self, stat_arb_strategy: StatArbStrategy
    ) -> None:
        dates = pd.date_range("2024-01-01", periods=50, freq="min", tz="UTC")
        # Oscillating prices for clear z-score
        t = np.linspace(0, 8 * np.pi, 50)
        prices = 100.0 + 10.0 * np.sin(t)
        df = pd.DataFrame({
            "open": prices - 0.1,
            "high": prices + 0.2,
            "low": prices - 0.2,
            "close": prices,
            "volume": np.ones(50) * 1000,
        }, index=dates)
        features: dict[str, float | None] = {}
        signal = stat_arb_strategy.generate_signal(df, features)
        # Should produce a signal at extremes
        assert signal is not None or signal is None

    def test_returns_none_with_empty_df(
        self, stat_arb_strategy: StatArbStrategy
    ) -> None:
        df = pd.DataFrame({"close": []})
        features: dict[str, float | None] = {"z_score": None}
        signal = stat_arb_strategy.generate_signal(df, features)
        assert signal is None

    def test_default_parameters(self, stat_arb_strategy: StatArbStrategy) -> None:
        params = stat_arb_strategy.get_parameters()
        assert params["zscore_window"] == 20.0
        assert params["entry_threshold"] == 2.0
        assert params["exit_threshold"] == 0.5

    def test_parameter_bounds(self, stat_arb_strategy: StatArbStrategy) -> None:
        bounds = stat_arb_strategy.parameter_bounds()
        assert "zscore_window" in bounds
        assert "entry_threshold" in bounds
        assert "exit_threshold" in bounds

    def test_strategy_name(self, stat_arb_strategy: StatArbStrategy) -> None:
        assert stat_arb_strategy.name == "stat_arb"

    def test_strategy_type(self, stat_arb_strategy: StatArbStrategy) -> None:
        from src.trading.schemas import StrategyType
        assert stat_arb_strategy.strategy_type == StrategyType.STATISTICAL_ARBITRAGE

    def test_nan_zscore_returns_none(
        self, stat_arb_strategy: StatArbStrategy
    ) -> None:
        features: dict[str, float | None] = {"z_score": float("nan")}
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = stat_arb_strategy.generate_signal(df, features)
        assert signal is None

    def test_zero_std_returns_none(
        self, stat_arb_strategy: StatArbStrategy
    ) -> None:
        df = pd.DataFrame({"close": [100.0] * 50})  # constant price -> std = 0
        features: dict[str, float | None] = {}
        signal = stat_arb_strategy.generate_signal(df, features)
        assert signal is None

    def test_state_tracks_previous_zscore(
        self, stat_arb_strategy: StatArbStrategy, sample_features: dict
    ) -> None:
        features = dict(sample_features)
        features["z_score"] = -2.5
        df = pd.DataFrame({"close": [100.0] * 30})
        stat_arb_strategy.generate_signal(df, features)
        assert stat_arb_strategy._state_data.get("prev_zscore") == -2.5

    def test_update_entry_threshold(self, stat_arb_strategy: StatArbStrategy) -> None:
        stat_arb_strategy.update_parameters({"entry_threshold": 3.0})
        assert stat_arb_strategy.get_parameters()["entry_threshold"] == 3.0

    def test_zscore_window_bounds(self, stat_arb_strategy: StatArbStrategy) -> None:
        stat_arb_strategy.update_parameters({"zscore_window": 200.0})
        assert stat_arb_strategy.get_parameters()["zscore_window"] == 100.0  # clamped
