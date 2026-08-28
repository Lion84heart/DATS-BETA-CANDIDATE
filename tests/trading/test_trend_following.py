"""Tests for the Trend Following Strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.trading.schemas import SignalDirection
from src.trading.strategies.trend_following import TrendFollowingStrategy


class TestTrendFollowingSignalGeneration:
    """Tests for trend following signal generation."""

    def test_buy_signal_when_fast_above_slow_and_high_adx(
        self, trend_strategy: TrendFollowingStrategy, sample_features: dict
    ) -> None:
        features = dict(sample_features)
        features["ema_9"] = 105.0  # fast > slow
        features["ema_21"] = 100.0
        features["adx_14"] = 30.0  # above threshold of 25
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = trend_strategy.generate_signal(df, features)
        assert signal is not None
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence > 0.5

    def test_sell_signal_when_fast_below_slow_and_high_adx(
        self, trend_strategy: TrendFollowingStrategy, sample_features: dict
    ) -> None:
        features = dict(sample_features)
        features["ema_9"] = 95.0  # fast < slow
        features["ema_21"] = 100.0
        features["adx_14"] = 30.0
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = trend_strategy.generate_signal(df, features)
        assert signal is not None
        assert signal.direction == SignalDirection.SELL
        assert signal.confidence > 0.5

    def test_no_signal_when_adx_below_threshold(
        self, trend_strategy: TrendFollowingStrategy, sample_features: dict
    ) -> None:
        features = dict(sample_features)
        features["ema_9"] = 105.0
        features["ema_21"] = 100.0
        features["adx_14"] = 15.0  # below threshold
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = trend_strategy.generate_signal(df, features)
        assert signal is None

    def test_no_signal_when_emas_equal(
        self, trend_strategy: TrendFollowingStrategy, sample_features: dict
    ) -> None:
        features = dict(sample_features)
        features["ema_9"] = 100.0
        features["ema_21"] = 100.0
        features["adx_14"] = 30.0
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = trend_strategy.generate_signal(df, features)
        assert signal is None

    def test_no_signal_when_missing_adx(
        self, trend_strategy: TrendFollowingStrategy, sample_features: dict
    ) -> None:
        features = dict(sample_features)
        features["ema_9"] = 105.0
        features["ema_21"] = 100.0
        features["adx_14"] = None
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = trend_strategy.generate_signal(df, features)
        assert signal is None

    def test_confidence_increases_with_adx_strength(
        self, trend_strategy: TrendFollowingStrategy, sample_features: dict
    ) -> None:
        features = dict(sample_features)
        features["ema_9"] = 110.0
        features["ema_21"] = 100.0
        features["adx_14"] = 50.0  # very strong trend
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = trend_strategy.generate_signal(df, features)
        assert signal is not None
        assert signal.confidence > 0.6

    def test_signal_reason_contains_context(
        self, trend_strategy: TrendFollowingStrategy, sample_features: dict
    ) -> None:
        features = dict(sample_features)
        features["ema_9"] = 105.0
        features["ema_21"] = 100.0
        features["adx_14"] = 30.0
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = trend_strategy.generate_signal(df, features)
        assert signal is not None
        assert "EMA" in signal.reason
        assert "ADX" in signal.reason

    def test_uses_ohlcv_fallback_when_features_missing(
        self, trend_strategy: TrendFollowingStrategy
    ) -> None:
        dates = pd.date_range("2024-01-01", periods=50, freq="min", tz="UTC")
        prices = np.linspace(100, 150, 50)  # clear upward trend
        df = pd.DataFrame({
            "open": prices - 0.5,
            "high": prices + 1.0,
            "low": prices - 1.0,
            "close": prices,
            "volume": np.ones(50) * 1000,
        }, index=dates)
        features = {"adx_14": 30.0}  # Only ADX provided, EMAs computed from OHLCV
        signal = trend_strategy.generate_signal(df, features)
        assert signal is not None
        assert signal.direction == SignalDirection.BUY

    def test_returns_none_with_empty_dataframe(
        self, trend_strategy: TrendFollowingStrategy
    ) -> None:
        df = pd.DataFrame({"close": []})
        features: dict[str, float | None] = {"ema_9": None, "ema_21": None, "adx_14": None}
        signal = trend_strategy.generate_signal(df, features)
        assert signal is None

    def test_buy_signal_on_trending_data(
        self, trend_strategy: TrendFollowingStrategy, sample_ohlcv_trend: pd.DataFrame
    ) -> None:
        from src.data.features import FeatureEngine
        engine = FeatureEngine()
        features = engine.compute_features(sample_ohlcv_trend)
        signal = trend_strategy.generate_signal(sample_ohlcv_trend, features)
        # On trending data, should eventually generate a signal
        assert signal is not None

    def test_default_parameters(self, trend_strategy: TrendFollowingStrategy) -> None:
        params = trend_strategy.get_parameters()
        assert params["fast_ema"] == 9.0
        assert params["slow_ema"] == 21.0
        assert params["adx_threshold"] == 25.0

    def test_parameter_bounds(self, trend_strategy: TrendFollowingStrategy) -> None:
        bounds = trend_strategy.parameter_bounds()
        assert bounds["fast_ema"] == (3.0, 50.0)
        assert bounds["slow_ema"] == (10.0, 200.0)
        assert bounds["adx_threshold"] == (10.0, 50.0)

    def test_strategy_name(self, trend_strategy: TrendFollowingStrategy) -> None:
        assert trend_strategy.name == "trend_following"

    def test_strategy_type(self, trend_strategy: TrendFollowingStrategy) -> None:
        from src.trading.schemas import StrategyType
        assert trend_strategy.strategy_type == StrategyType.TREND_FOLLOWING

    def test_nan_features_handled_gracefully(
        self, trend_strategy: TrendFollowingStrategy
    ) -> None:
        import math
        features: dict[str, float | None] = {
            "ema_9": float("nan"),
            "ema_21": float("nan"),
            "adx_14": float("nan"),
        }
        df = pd.DataFrame({"close": [100.0] * 30})
        signal = trend_strategy.generate_signal(df, features)
        assert signal is None
