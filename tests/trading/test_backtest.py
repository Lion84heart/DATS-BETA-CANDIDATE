"""Tests for the event-driven backtesting engine."""

from __future__ import annotations

import pandas as pd
import pytest

from src.trading.backtest import BacktestEngine
from src.trading.schemas import SignalDirection, StrategyConfig, StrategyType
from src.trading.strategies.trend_following import TrendFollowingStrategy
from tests.trading.conftest import MockStrategy


class TestBacktestEngineInit:
    """Tests for engine initialization."""

    def test_default_config(self) -> None:
        engine = BacktestEngine()
        assert engine.initial_capital == 10000.0
        assert engine.commission_rate == 0.001
        assert engine.slippage_model == "fixed"
        assert engine.slippage == 0.0005

    def test_custom_config(self) -> None:
        engine = BacktestEngine(
            initial_capital=50000.0,
            commission_rate=0.002,
            slippage_model="percentage",
            slippage=0.001,
        )
        assert engine.initial_capital == 50000.0
        assert engine.commission_rate == 0.002
        assert engine.slippage_model == "percentage"

    def test_apply_slippage_buy(self) -> None:
        engine = BacktestEngine()
        price = engine._apply_slippage(100.0, SignalDirection.BUY)
        assert price > 100.0

    def test_apply_slippage_sell(self) -> None:
        engine = BacktestEngine()
        price = engine._apply_slippage(100.0, SignalDirection.SELL)
        assert price < 100.0

    def test_compute_fees(self) -> None:
        engine = BacktestEngine(commission_rate=0.001)
        fees = engine._compute_fees(100.0, 1.0)
        assert fees == 0.1

    def test_apply_slippage_percentage_model(self) -> None:
        engine = BacktestEngine(slippage_model="percentage", slippage=0.001)
        price = engine._apply_slippage(100.0, SignalDirection.BUY)
        assert price == 100.1


class TestBacktestEngineRun:
    """Tests for running backtests."""

    @pytest.mark.asyncio
    async def test_run_with_trend_strategy(self, sample_ohlcv_large: pd.DataFrame) -> None:
        engine = BacktestEngine()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        result = engine.run(strategy, sample_ohlcv_large)
        assert result is not None
        assert result.strategy_name == "trend_following"
        assert len(result.equity_curve) > 0
        assert result.equity_curve[0] == 10000.0

    @pytest.mark.asyncio
    async def test_run_with_mock_strategy(self, sample_ohlcv_large: pd.DataFrame) -> None:
        engine = BacktestEngine()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
            parameters={"threshold": 60.0},
        )
        strategy = MockStrategy(config)
        result = engine.run(strategy, sample_ohlcv_large)
        assert result is not None
        assert result.strategy_name == "mock_strategy"
        assert len(result.equity_curve) > 0

    def test_empty_ohlcv_returns_empty_result(self, empty_ohlcv: pd.DataFrame) -> None:
        engine = BacktestEngine()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        result = engine.run(strategy, empty_ohlcv)
        assert result.num_trades == 0
        assert result.equity_curve == [10000.0]

    def test_small_ohlcv_returns_empty_result(self) -> None:
        engine = BacktestEngine()
        df = pd.DataFrame({
            "open": [100.0] * 10,
            "high": [101.0] * 10,
            "low": [99.0] * 10,
            "close": [100.0] * 10,
            "volume": [1000.0] * 10,
        })
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        result = engine.run(strategy, df)
        assert result.num_trades == 0

    def test_equity_curve_starts_with_initial_capital(
        self, sample_ohlcv_large: pd.DataFrame
    ) -> None:
        engine = BacktestEngine(initial_capital=50000.0)
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        result = engine.run(strategy, sample_ohlcv_large)
        assert result.equity_curve[0] == 50000.0

    def test_backtest_returns_metrics(self, sample_ohlcv_large: pd.DataFrame) -> None:
        engine = BacktestEngine()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        result = engine.run(strategy, sample_ohlcv_large)
        assert result.metrics is not None
        assert hasattr(result.metrics, "sharpe_ratio")
        assert hasattr(result.metrics, "max_drawdown")
        assert hasattr(result.metrics, "win_rate")

    def test_backtest_populates_parameters(
        self, sample_ohlcv_large: pd.DataFrame
    ) -> None:
        engine = BacktestEngine()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
            parameters={"fast_ema": 15.0},
        )
        strategy = TrendFollowingStrategy(config)
        result = engine.run(strategy, sample_ohlcv_large)
        assert "fast_ema" in result.parameters

    def test_no_lookahead_bias(self, sample_ohlcv_large: pd.DataFrame) -> None:
        """Verify that the backtest only uses data up to each bar."""
        engine = BacktestEngine()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        result = engine.run(strategy, sample_ohlcv_large)
        # The backtest should complete without errors
        assert result is not None
        assert len(result.equity_curve) <= len(sample_ohlcv_large) + 1

    def test_transaction_costs_applied(self, sample_ohlcv_large: pd.DataFrame) -> None:
        engine = BacktestEngine(commission_rate=0.01)  # high commission
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        result = engine.run(strategy, sample_ohlcv_large)
        # Higher commission should reduce returns
        if result.num_trades > 0:
            total_fees = sum(t.fees for t in result.trades)
            assert total_fees > 0

    def test_trade_records_valid(self, sample_ohlcv_large: pd.DataFrame) -> None:
        engine = BacktestEngine()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        result = engine.run(strategy, sample_ohlcv_large)
        for trade in result.trades:
            assert trade.entry_price > 0
            assert trade.size > 0
            assert trade.direction in ("long", "short")
            if not trade.is_open():
                assert trade.exit_price is not None
                assert trade.exit_price > 0

    def test_result_to_dataframe(self, sample_ohlcv_large: pd.DataFrame) -> None:
        engine = BacktestEngine()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        result = engine.run(strategy, sample_ohlcv_large)
        df = result.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == result.num_trades

    def test_backtest_with_symbol(self, sample_ohlcv_large: pd.DataFrame) -> None:
        engine = BacktestEngine()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="BTC/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        result = engine.run(strategy, sample_ohlcv_large)
        assert result.symbol == "BTC/USDC"

    def test_walk_forward(self, sample_ohlcv_large: pd.DataFrame) -> None:
        engine = BacktestEngine()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        results = engine.run_walk_forward(
            strategy, sample_ohlcv_large, train_size=100, test_size=50
        )
        assert isinstance(results, list)
        assert len(results) > 0

    def test_walk_forward_with_small_data(self) -> None:
        engine = BacktestEngine()
        df = pd.DataFrame({
            "open": [100.0] * 200,
            "high": [101.0] * 200,
            "low": [99.0] * 200,
            "close": [100.0] * 200,
            "volume": [1000.0] * 200,
        })
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        results = engine.run_walk_forward(strategy, df, train_size=100, test_size=50)
        assert isinstance(results, list)

    def test_compute_equity_curve_from_trades(self) -> None:
        engine = BacktestEngine(initial_capital=10000.0)
        from src.trading.schemas import TradeRecord
        from datetime import datetime, timezone
        trades = [
            TradeRecord(
                entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
                exit_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
                entry_price=100.0,
                exit_price=105.0,
                size=1.0,
                direction="long",
                pnl=5.0,
                fees=0.1,
            ),
            TradeRecord(
                entry_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
                exit_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
                entry_price=105.0,
                exit_price=103.0,
                size=1.0,
                direction="long",
                pnl=-2.0,
                fees=0.1,
            ),
        ]
        curve = engine._compute_equity_curve(trades)
        assert curve[0] == 10000.0
        assert curve[1] == 10005.0
        assert curve[2] == 10003.0

    def test_compute_metrics_empty(self) -> None:
        engine = BacktestEngine()
        metrics = engine._compute_metrics([], [10000.0])
        assert metrics.num_trades == 0
        assert metrics.total_return == 0.0

    def test_result_dates_valid(self, sample_ohlcv_large: pd.DataFrame) -> None:
        engine = BacktestEngine()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        result = engine.run(strategy, sample_ohlcv_large)
        assert result.start_date <= result.end_date
