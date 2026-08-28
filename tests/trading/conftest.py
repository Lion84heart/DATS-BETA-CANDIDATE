"""Shared fixtures for strategy engine tests."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from src.trading.base_strategy import BaseStrategy
from src.trading.schemas import (
    PerformanceMetrics,
    SignalDirection,
    StrategyConfig,
    StrategySignal,
    StrategyType,
)
from src.trading.strategies.breakout import BreakoutStrategy
from src.trading.strategies.mean_reversion import MeanReversionStrategy
from src.trading.strategies.momentum import MomentumStrategy
from src.trading.strategies.stat_arb import StatArbStrategy
from src.trading.strategies.trend_following import TrendFollowingStrategy


# ---------------------------------------------------------------------------
# Sample OHLCV Data
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Return a small sample OHLCV DataFrame."""
    dates = pd.date_range("2024-01-01", periods=50, freq="min", tz="UTC")
    np.random.seed(42)
    base = 100.0
    prices = [base]
    for _ in range(1, 50):
        prices.append(prices[-1] * (1 + np.random.normal(0, 0.001)))
    prices = np.array(prices)
    df = pd.DataFrame({
        "open": prices * (1 + np.random.normal(0, 0.0005, 50)),
        "high": prices * (1 + abs(np.random.normal(0, 0.001, 50))),
        "low": prices * (1 - abs(np.random.normal(0, 0.001, 50))),
        "close": prices,
        "volume": np.random.uniform(1000, 5000, 50),
    }, index=dates)
    return df


@pytest.fixture
def sample_ohlcv_trend() -> pd.DataFrame:
    """Return OHLCV data with a clear upward trend."""
    dates = pd.date_range("2024-01-01", periods=100, freq="min", tz="UTC")
    base = 100.0
    prices = []
    for i in range(100):
        prices.append(base + i * 0.1 + np.random.normal(0, 0.05))
    prices = np.array(prices)
    df = pd.DataFrame({
        "open": prices - 0.02,
        "high": prices + 0.05,
        "low": prices - 0.05,
        "close": prices,
        "volume": np.random.uniform(1000, 5000, 100),
    }, index=dates)
    return df


@pytest.fixture
def sample_ohlcv_ranging() -> pd.DataFrame:
    """Return OHLCV data that oscillates in a range (mean-reversion friendly)."""
    dates = pd.date_range("2024-01-01", periods=100, freq="min", tz="UTC")
    t = np.linspace(0, 8 * np.pi, 100)
    prices = 100.0 + 5.0 * np.sin(t) + np.random.normal(0, 0.2, 100)
    df = pd.DataFrame({
        "open": prices - 0.1,
        "high": prices + 0.2,
        "low": prices - 0.2,
        "close": prices,
        "volume": np.random.uniform(1000, 5000, 100),
    }, index=dates)
    return df


@pytest.fixture
def sample_ohlcv_large() -> pd.DataFrame:
    """Return a larger OHLCV DataFrame for thorough testing."""
    dates = pd.date_range("2024-01-01", periods=500, freq="min", tz="UTC")
    np.random.seed(123)
    base = 100.0
    prices = [base]
    for _ in range(1, 500):
        prices.append(prices[-1] * (1 + np.random.normal(0.0001, 0.005)))
    prices = np.array(prices)
    df = pd.DataFrame({
        "open": prices * (1 + np.random.normal(0, 0.001, 500)),
        "high": prices * (1 + abs(np.random.normal(0, 0.003, 500))),
        "low": prices * (1 - abs(np.random.normal(0, 0.003, 500))),
        "close": prices,
        "volume": np.random.uniform(1000, 10000, 500),
    }, index=dates)
    return df


@pytest.fixture
def sample_ohlcv_fast() -> pd.DataFrame:
    """Return a small OHLCV DataFrame for fast optimization/AB tests."""
    dates = pd.date_range("2024-01-01", periods=150, freq="min", tz="UTC")
    np.random.seed(456)
    base = 100.0
    prices = [base]
    for _ in range(1, 150):
        prices.append(prices[-1] * (1 + np.random.normal(0.0001, 0.005)))
    prices = np.array(prices)
    df = pd.DataFrame({
        "open": prices * (1 + np.random.normal(0, 0.001, 150)),
        "high": prices * (1 + abs(np.random.normal(0, 0.003, 150))),
        "low": prices * (1 - abs(np.random.normal(0, 0.003, 150))),
        "close": prices,
        "volume": np.random.uniform(1000, 10000, 150),
    }, index=dates)
    return df


@pytest.fixture
def empty_ohlcv() -> pd.DataFrame:
    """Return an empty OHLCV DataFrame."""
    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])


# ---------------------------------------------------------------------------
# Strategy Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def trend_config() -> StrategyConfig:
    return StrategyConfig(
        strategy_type=StrategyType.TREND_FOLLOWING,
        symbol="SOL/USDC",
        parameters={"fast_ema": 9, "slow_ema": 21, "adx_threshold": 25},
    )


@pytest.fixture
def trend_strategy(trend_config: StrategyConfig) -> TrendFollowingStrategy:
    return TrendFollowingStrategy(trend_config)


@pytest.fixture
def mean_reversion_config() -> StrategyConfig:
    return StrategyConfig(
        strategy_type=StrategyType.MEAN_REVERSION,
        symbol="SOL/USDC",
        parameters={
            "bb_period": 20,
            "bb_std": 2.0,
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
        },
    )


@pytest.fixture
def mean_reversion_strategy(mean_reversion_config: StrategyConfig) -> MeanReversionStrategy:
    return MeanReversionStrategy(mean_reversion_config)


@pytest.fixture
def momentum_config() -> StrategyConfig:
    return StrategyConfig(
        strategy_type=StrategyType.MOMENTUM,
        symbol="SOL/USDC",
        parameters={
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "volume_threshold": 1.5,
        },
    )


@pytest.fixture
def momentum_strategy(momentum_config: StrategyConfig) -> MomentumStrategy:
    return MomentumStrategy(momentum_config)


@pytest.fixture
def breakout_config() -> StrategyConfig:
    return StrategyConfig(
        strategy_type=StrategyType.BREAKOUT,
        symbol="SOL/USDC",
        parameters={"lookback": 20, "atr_multiplier": 1.5, "volume_threshold": 2.0},
    )


@pytest.fixture
def breakout_strategy(breakout_config: StrategyConfig) -> BreakoutStrategy:
    return BreakoutStrategy(breakout_config)


@pytest.fixture
def stat_arb_config() -> StrategyConfig:
    return StrategyConfig(
        strategy_type=StrategyType.STATISTICAL_ARBITRAGE,
        symbol="SOL/USDC",
        parameters={"zscore_window": 20, "entry_threshold": 2.0, "exit_threshold": 0.5},
    )


@pytest.fixture
def stat_arb_strategy(stat_arb_config: StrategyConfig) -> StatArbStrategy:
    return StatArbStrategy(stat_arb_config)


# ---------------------------------------------------------------------------
# Feature Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_features() -> dict[str, float | None]:
    return {
        "rsi_14": 65.0,
        "rsi_7": 70.0,
        "macd": 0.5,
        "macd_signal": 0.3,
        "macd_histogram": 0.2,
        "bb_upper": 110.0,
        "bb_lower": 90.0,
        "bb_width": 0.2,
        "bb_pct_b": 0.65,
        "ema_9": 102.0,
        "ema_21": 101.0,
        "ema_50": 100.0,
        "sma_20": 100.5,
        "sma_50": 99.5,
        "sma_200": 98.0,
        "atr_14": 1.5,
        "adx_14": 28.0,
        "plus_di": 25.0,
        "minus_di": 15.0,
        "dist_from_vwap": 0.01,
        "dist_from_ema50": 0.02,
        "return_1m": 0.001,
        "return_5m": 0.005,
        "return_15m": 0.01,
        "return_1h": 0.03,
        "skewness": 0.1,
        "kurtosis": 3.0,
        "z_score": 0.5,
        "relative_volume": 1.2,
        "volume_change": 0.05,
        "realized_vol_20": 0.02,
        "close": 102.0,
        "volume": 5000.0,
    }


@pytest.fixture
def empty_features() -> dict[str, float | None]:
    feature_names = [
        "rsi_14", "rsi_7", "macd", "macd_signal", "macd_histogram",
        "bb_upper", "bb_lower", "bb_width", "bb_pct_b",
        "ema_9", "ema_21", "ema_50", "sma_20", "sma_50", "sma_200",
        "atr_14", "adx_14", "plus_di", "minus_di",
        "z_score", "relative_volume",
    ]
    return {name: None for name in feature_names}


# ---------------------------------------------------------------------------
# Mock Strategy for Testing Base
# ---------------------------------------------------------------------------


class MockStrategy(BaseStrategy):
    """Concrete mock strategy for testing the base class."""

    name = "mock_strategy"
    strategy_type = StrategyType.TREND_FOLLOWING

    _DEFAULT_THRESHOLD: float = 50.0

    def _apply_defaults(self) -> None:
        if "threshold" not in self.parameters:
            self.parameters["threshold"] = self._DEFAULT_THRESHOLD
        self.config.parameters = dict(self.parameters)

    def parameter_bounds(self) -> dict[str, tuple[float, float]]:
        return {"threshold": (0.0, 100.0)}

    def generate_signal(
        self,
        ohlcv_df: pd.DataFrame,
        features: dict[str, float | None],
    ) -> StrategySignal | None:
        rsi = self._safe_feature(features, "rsi_14")
        threshold = self.parameters.get("threshold", self._DEFAULT_THRESHOLD)
        if rsi is None:
            return None
        if rsi > threshold:
            return self._create_signal(
                direction=SignalDirection.BUY,
                confidence=0.7,
                reason=f"RSI {rsi:.1f} > threshold {threshold}",
                features=features,
            )
        elif rsi < (100 - threshold):
            return self._create_signal(
                direction=SignalDirection.SELL,
                confidence=0.7,
                reason=f"RSI {rsi:.1f} < threshold {100 - threshold}",
                features=features,
            )
        return None


@pytest.fixture
def mock_strategy() -> MockStrategy:
    config = StrategyConfig(
        strategy_type=StrategyType.TREND_FOLLOWING,
        symbol="SOL/USDC",
        parameters={"threshold": 60.0},
    )
    return MockStrategy(config)


@pytest.fixture
def sample_backtest_result():
    """Return a sample BacktestResult for performance tracker tests."""
    from src.trading.schemas import BacktestResult, TradeRecord

    trades = [
        TradeRecord(
            entry_time=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc),
            entry_price=100.0,
            exit_price=105.0,
            size=1.0,
            direction="long",
            pnl=5.0,
            fees=0.1,
            signal_id="sig_1",
        ),
        TradeRecord(
            entry_time=datetime(2024, 1, 1, 2, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 1, 1, 3, 0, tzinfo=timezone.utc),
            entry_price=105.0,
            exit_price=103.0,
            size=1.0,
            direction="short",
            pnl=2.0,
            fees=0.1,
            signal_id="sig_2",
        ),
    ]
    metrics = PerformanceMetrics(
        total_return=0.07,
        sharpe_ratio=1.5,
        max_drawdown=0.03,
        win_rate=1.0,
        profit_factor=7.0,
        num_trades=2,
        expectancy=3.4,
    )
    return BacktestResult(
        strategy_name="mock_strategy",
        symbol="SOL/USDC",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
        total_return=0.07,
        sharpe_ratio=1.5,
        max_drawdown=0.03,
        win_rate=1.0,
        num_trades=2,
        avg_trade_return=0.035,
        profit_factor=7.0,
        equity_curve=[10000.0, 10005.0, 10007.0],
        trades=trades,
        parameters={"threshold": 60.0},
        metrics=metrics,
    )


@pytest.fixture
def sample_ab_test():
    """Return a sample ABTest configuration."""
    from src.trading.schemas import ABTest
    return ABTest(
        name="trend_vs_mean_rev",
        strategy_a_name="trend_following",
        strategy_b_name="mean_reversion",
        confidence_level=0.95,
    )
