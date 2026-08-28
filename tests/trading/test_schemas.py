"""Tests for trading engine Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest
from pydantic import ValidationError

from src.trading.schemas import (
    ABTest,
    ABTestResult,
    BacktestResult,
    PerformanceMetrics,
    SignalDirection,
    StrategyConfig,
    StrategySignal,
    StrategyState,
    StrategyType,
    TradeRecord,
)


class TestStrategyType:
    """15+ tests for StrategyType enum."""

    def test_all_values_present(self) -> None:
        assert StrategyType.TREND_FOLLOWING.value == "trend_following"
        assert StrategyType.MEAN_REVERSION.value == "mean_reversion"
        assert StrategyType.MOMENTUM.value == "momentum"
        assert StrategyType.BREAKOUT.value == "breakout"
        assert StrategyType.STATISTICAL_ARBITRAGE.value == "statistical_arbitrage"

    def test_five_strategy_types(self) -> None:
        assert len(StrategyType) == 5

    def test_from_string(self) -> None:
        assert StrategyType("trend_following") == StrategyType.TREND_FOLLOWING
        assert StrategyType("mean_reversion") == StrategyType.MEAN_REVERSION

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            StrategyType("invalid_type")


class TestSignalDirection:
    """Tests for SignalDirection enum."""

    def test_values(self) -> None:
        assert SignalDirection.BUY.value == "BUY"
        assert SignalDirection.SELL.value == "SELL"
        assert SignalDirection.HOLD.value == "HOLD"

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            SignalDirection("INVALID")


class TestStrategyConfig:
    """Tests for StrategyConfig model."""

    def test_valid_config(self) -> None:
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
            parameters={"fast_ema": 9.0},
            enabled=True,
        )
        assert config.strategy_type == StrategyType.TREND_FOLLOWING
        assert config.symbol == "SOL/USDC"
        assert config.parameters["fast_ema"] == 9.0
        assert config.enabled is True

    def test_default_enabled(self) -> None:
        config = StrategyConfig(
            strategy_type=StrategyType.MOMENTUM,
            symbol="BTC/USDC",
        )
        assert config.enabled is True
        assert config.parameters == {}

    def test_default_timestamp(self) -> None:
        config = StrategyConfig(
            strategy_type=StrategyType.BREAKOUT,
            symbol="ETH/USDC",
        )
        assert config.timestamp.tzinfo is not None

    def test_timestamp_from_string(self) -> None:
        config = StrategyConfig(
            strategy_type=StrategyType.MEAN_REVERSION,
            symbol="SOL/USDC",
            timestamp="2024-01-01T00:00:00Z",
        )
        assert config.timestamp.year == 2024

    def test_naive_timestamp_gets_utc(self) -> None:
        config = StrategyConfig(
            strategy_type=StrategyType.STATISTICAL_ARBITRAGE,
            symbol="SOL/USDC",
            timestamp=datetime(2024, 1, 1, 0, 0),
        )
        assert config.timestamp.tzinfo == timezone.utc


class TestStrategySignal:
    """Tests for StrategySignal model."""

    def test_valid_signal(self) -> None:
        signal = StrategySignal(
            symbol="SOL/USDC",
            direction=SignalDirection.BUY,
            confidence=0.85,
            reason="EMA crossover",
            features_used={"rsi_14": 65.0, "ema_9": 102.0},
            strategy_name="trend_following",
            parameters_used={"fast_ema": 9.0},
        )
        assert signal.confidence == 0.85
        assert signal.direction == SignalDirection.BUY

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            StrategySignal(
                symbol="SOL/USDC",
                direction=SignalDirection.BUY,
                confidence=1.5,
                strategy_name="test",
            )

    def test_confidence_negative_raises(self) -> None:
        with pytest.raises(ValidationError):
            StrategySignal(
                symbol="SOL/USDC",
                direction=SignalDirection.SELL,
                confidence=-0.1,
                strategy_name="test",
            )

    def test_default_timestamp(self) -> None:
        signal = StrategySignal(
            symbol="SOL/USDC",
            direction=SignalDirection.HOLD,
            confidence=0.5,
            strategy_name="test",
        )
        assert signal.timestamp.tzinfo is not None

    def test_hold_direction(self) -> None:
        signal = StrategySignal(
            symbol="SOL/USDC",
            direction=SignalDirection.HOLD,
            confidence=0.0,
            strategy_name="test",
        )
        assert signal.direction == SignalDirection.HOLD

    def test_features_used_none_values(self) -> None:
        signal = StrategySignal(
            symbol="SOL/USDC",
            direction=SignalDirection.BUY,
            confidence=0.7,
            strategy_name="test",
            features_used={"rsi_14": None, "ema_9": 102.0},
        )
        assert signal.features_used["rsi_14"] is None


class TestTradeRecord:
    """Tests for TradeRecord model."""

    def test_valid_trade(self) -> None:
        trade = TradeRecord(
            entry_time=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
            entry_price=100.0,
            size=1.0,
            direction="long",
        )
        assert trade.entry_price == 100.0
        assert trade.is_open() is True

    def test_closed_trade(self) -> None:
        trade = TradeRecord(
            entry_time=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 1, 1, 1, 0, tzinfo=timezone.utc),
            entry_price=100.0,
            exit_price=105.0,
            size=1.0,
            direction="long",
            pnl=5.0,
            fees=0.1,
        )
        assert trade.is_open() is False
        assert trade.pnl == 5.0

    def test_entry_price_positive(self) -> None:
        with pytest.raises(ValidationError):
            TradeRecord(
                entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
                entry_price=0.0,
                size=1.0,
                direction="long",
            )

    def test_size_positive(self) -> None:
        with pytest.raises(ValidationError):
            TradeRecord(
                entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
                entry_price=100.0,
                size=0.0,
                direction="long",
            )

    def test_short_direction(self) -> None:
        trade = TradeRecord(
            entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            entry_price=100.0,
            size=1.0,
            direction="short",
        )
        assert trade.direction == "short"

    def test_invalid_direction(self) -> None:
        with pytest.raises(ValidationError):
            TradeRecord(
                entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
                entry_price=100.0,
                size=1.0,
                direction="invalid",
            )

    def test_naive_timestamp_converted(self) -> None:
        trade = TradeRecord(
            entry_time=datetime(2024, 1, 1, 0, 0),
            entry_price=100.0,
            size=1.0,
            direction="long",
        )
        assert trade.entry_time.tzinfo == timezone.utc


class TestPerformanceMetrics:
    """Tests for PerformanceMetrics model."""

    def test_defaults(self) -> None:
        m = PerformanceMetrics()
        assert m.total_return == 0.0
        assert m.sharpe_ratio == 0.0
        assert m.num_trades == 0

    def test_valid_metrics(self) -> None:
        m = PerformanceMetrics(
            total_return=0.15,
            sharpe_ratio=1.8,
            max_drawdown=0.05,
            win_rate=0.65,
            num_trades=100,
        )
        assert m.win_rate == 0.65

    def test_win_rate_bounds(self) -> None:
        with pytest.raises(ValidationError):
            PerformanceMetrics(win_rate=1.5)
        with pytest.raises(ValidationError):
            PerformanceMetrics(win_rate=-0.1)

    def test_all_fields(self) -> None:
        m = PerformanceMetrics(
            total_return=0.1,
            annualized_return=0.25,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.05,
            max_drawdown_duration=10,
            calmar_ratio=5.0,
            win_rate=0.6,
            profit_factor=2.0,
            avg_win=100.0,
            avg_loss=-50.0,
            expectancy=25.0,
            num_trades=50,
            avg_holding_period=5.0,
            volatility=0.2,
            skewness=0.1,
            kurtosis=3.0,
        )
        assert m.expectancy == 25.0
        assert m.calmar_ratio == 5.0


class TestBacktestResult:
    """Tests for BacktestResult model."""

    def test_valid_result(self, sample_backtest_result: BacktestResult) -> None:
        assert sample_backtest_result.strategy_name == "mock_strategy"
        assert sample_backtest_result.num_trades == 2
        assert len(sample_backtest_result.equity_curve) == 3

    def test_empty_trades(self) -> None:
        result = BacktestResult(
            strategy_name="test",
            symbol="SOL/USDC",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
        )
        assert result.num_trades == 0
        df = result.to_dataframe()
        assert df.empty

    def test_to_dataframe(self, sample_backtest_result: BacktestResult) -> None:
        df = sample_backtest_result.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "pnl" in df.columns

    def test_parameters_roundtrip(self) -> None:
        params = {"fast_ema": 9.0, "slow_ema": 21.0}
        result = BacktestResult(
            strategy_name="test",
            symbol="SOL/USDC",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
            parameters=params,
        )
        assert result.parameters == params


class TestABTest:
    """Tests for ABTest model."""

    def test_valid_test(self) -> None:
        test = ABTest(
            name="test_1",
            strategy_a_name="strategy_a",
            strategy_b_name="strategy_b",
            confidence_level=0.95,
        )
        assert test.name == "test_1"
        assert test.confidence_level == 0.95
        assert test.status == "pending"

    def test_default_confidence(self) -> None:
        test = ABTest(
            name="test_2",
            strategy_a_name="a",
            strategy_b_name="b",
        )
        assert test.confidence_level == 0.95

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ABTest(
                name="test",
                strategy_a_name="a",
                strategy_b_name="b",
                confidence_level=1.5,
            )


class TestABTestResult:
    """Tests for ABTestResult model."""

    def test_valid_result(self) -> None:
        metrics_a = PerformanceMetrics(sharpe_ratio=1.5, total_return=0.1)
        metrics_b = PerformanceMetrics(sharpe_ratio=1.2, total_return=0.08)
        result = ABTestResult(
            test_name="test_1",
            strategy_a_name="strategy_a",
            strategy_b_name="strategy_b",
            strategy_a_metrics=metrics_a,
            strategy_b_metrics=metrics_b,
            winner="A",
            p_value=0.03,
            confidence=0.95,
            recommendation="Deploy A",
        )
        assert result.winner == "A"
        assert result.p_value == 0.03

    def test_winner_must_be_valid(self) -> None:
        metrics = PerformanceMetrics()
        with pytest.raises(ValidationError):
            ABTestResult(
                test_name="test",
                strategy_a_name="a",
                strategy_b_name="b",
                strategy_a_metrics=metrics,
                strategy_b_metrics=metrics,
                winner="C",
                p_value=0.05,
                confidence=0.95,
            )

    def test_p_value_bounds(self) -> None:
        metrics = PerformanceMetrics()
        with pytest.raises(ValidationError):
            ABTestResult(
                test_name="test",
                strategy_a_name="a",
                strategy_b_name="b",
                strategy_a_metrics=metrics,
                strategy_b_metrics=metrics,
                winner="tie",
                p_value=1.5,
                confidence=0.95,
            )


class TestStrategyState:
    """Tests for StrategyState model."""

    def test_valid_state(self) -> None:
        state = StrategyState(
            name="trend_following",
            strategy_type=StrategyType.TREND_FOLLOWING,
            parameters={"fast_ema": 9.0},
            enabled=True,
        )
        assert state.name == "trend_following"
        assert state.enabled is True

    def test_state_data(self) -> None:
        state = StrategyState(
            name="test",
            strategy_type=StrategyType.MOMENTUM,
            state_data={"prev_signal": "BUY"},
        )
        assert state.state_data["prev_signal"] == "BUY"

    def test_default_timestamp(self) -> None:
        state = StrategyState(
            name="test",
            strategy_type=StrategyType.BREAKOUT,
        )
        assert state.last_updated.tzinfo is not None
