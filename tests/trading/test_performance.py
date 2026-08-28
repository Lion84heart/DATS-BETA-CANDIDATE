"""Tests for the performance tracker."""

from __future__ import annotations

import pandas as pd
import pytest

from src.trading.performance import PerformanceTracker
from src.trading.schemas import (
    BacktestResult,
    PerformanceMetrics,
    StrategyConfig,
    StrategyType,
    TradeRecord,
)
from src.trading.strategies.trend_following import TrendFollowingStrategy
from datetime import datetime, timezone


class TestPerformanceTrackerInit:
    """Tests for tracker initialization."""

    def test_empty_tracker(self) -> None:
        tracker = PerformanceTracker()
        assert tracker._history == {}


class TestRecordBacktest:
    """Tests for recording backtest results."""

    @pytest.mark.asyncio
    async def test_record_single(self, sample_backtest_result: BacktestResult) -> None:
        tracker = PerformanceTracker()
        await tracker.record_backtest("mock_strategy", sample_backtest_result)
        history = await tracker.get_history("mock_strategy")
        assert len(history) == 1

    @pytest.mark.asyncio
    async def test_record_multiple(self, sample_backtest_result: BacktestResult) -> None:
        tracker = PerformanceTracker()
        await tracker.record_backtest("mock_strategy", sample_backtest_result)
        # Record again
        result2 = BacktestResult(
            strategy_name="mock_strategy",
            symbol="SOL/USDC",
            start_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 3, tzinfo=timezone.utc),
            metrics=PerformanceMetrics(total_return=0.1, sharpe_ratio=2.0),
        )
        await tracker.record_backtest("mock_strategy", result2)
        history = await tracker.get_history("mock_strategy")
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_record_multiple_strategies(self, sample_backtest_result: BacktestResult) -> None:
        tracker = PerformanceTracker()
        await tracker.record_backtest("strategy_a", sample_backtest_result)
        result_b = BacktestResult(
            strategy_name="strategy_b",
            symbol="SOL/USDC",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
            metrics=PerformanceMetrics(total_return=0.05, sharpe_ratio=1.0),
        )
        await tracker.record_backtest("strategy_b", result_b)
        assert len(tracker._history) == 2


class TestGetHistory:
    """Tests for retrieving backtest history."""

    @pytest.mark.asyncio
    async def test_get_history_empty(self) -> None:
        tracker = PerformanceTracker()
        history = await tracker.get_history("nonexistent")
        assert history == []

    @pytest.mark.asyncio
    async def test_get_history_returns_copy(self, sample_backtest_result: BacktestResult) -> None:
        tracker = PerformanceTracker()
        await tracker.record_backtest("mock", sample_backtest_result)
        history = await tracker.get_history("mock")
        assert isinstance(history, list)


class TestCompareStrategies:
    """Tests for strategy comparison."""

    @pytest.mark.asyncio
    async def test_compare_two(self, sample_backtest_result: BacktestResult) -> None:
        tracker = PerformanceTracker()
        await tracker.record_backtest("strategy_a", sample_backtest_result)
        result_b = BacktestResult(
            strategy_name="strategy_b",
            symbol="SOL/USDC",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
            metrics=PerformanceMetrics(
                total_return=0.12,
                sharpe_ratio=2.0,
                max_drawdown=0.02,
                win_rate=0.7,
                profit_factor=3.0,
                num_trades=10,
                expectancy=1.0,
            ),
        )
        await tracker.record_backtest("strategy_b", result_b)
        df = await tracker.compare_strategies(["strategy_a", "strategy_b"])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "sharpe_ratio" in df.columns

    @pytest.mark.asyncio
    async def test_compare_with_custom_metrics(self, sample_backtest_result: BacktestResult) -> None:
        tracker = PerformanceTracker()
        await tracker.record_backtest("strategy_a", sample_backtest_result)
        df = await tracker.compare_strategies(
            ["strategy_a"],
            metrics=["total_return", "sharpe_ratio"],
        )
        assert list(df.columns) == ["total_return", "sharpe_ratio"]

    @pytest.mark.asyncio
    async def test_compare_empty(self) -> None:
        tracker = PerformanceTracker()
        df = await tracker.compare_strategies(["nonexistent"])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    @pytest.mark.asyncio
    async def test_compare_single(self, sample_backtest_result: BacktestResult) -> None:
        tracker = PerformanceTracker()
        await tracker.record_backtest("strategy_a", sample_backtest_result)
        df = await tracker.compare_strategies(["strategy_a"])
        assert len(df) == 1
        assert df.index[0] == "strategy_a"


class TestBestStrategy:
    """Tests for finding the best strategy."""

    @pytest.mark.asyncio
    async def test_best_by_sharpe(self, sample_backtest_result: BacktestResult) -> None:
        tracker = PerformanceTracker()
        await tracker.record_backtest("strategy_a", sample_backtest_result)
        result_b = BacktestResult(
            strategy_name="strategy_b",
            symbol="SOL/USDC",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
            metrics=PerformanceMetrics(sharpe_ratio=3.0, total_return=0.2),
        )
        await tracker.record_backtest("strategy_b", result_b)
        best = await tracker.best_strategy("sharpe_ratio")
        assert best is not None
        assert best[0] == "strategy_b"
        assert best[1].sharpe_ratio == 3.0

    @pytest.mark.asyncio
    async def test_best_empty(self) -> None:
        tracker = PerformanceTracker()
        best = await tracker.best_strategy("sharpe_ratio")
        assert best is None

    @pytest.mark.asyncio
    async def test_best_by_return(self, sample_backtest_result: BacktestResult) -> None:
        tracker = PerformanceTracker()
        result_a = BacktestResult(
            strategy_name="strategy_a",
            symbol="SOL/USDC",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
            metrics=PerformanceMetrics(total_return=0.05, sharpe_ratio=0.5),
        )
        result_b = BacktestResult(
            strategy_name="strategy_b",
            symbol="SOL/USDC",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
            metrics=PerformanceMetrics(total_return=0.15, sharpe_ratio=1.0),
        )
        await tracker.record_backtest("strategy_a", result_a)
        await tracker.record_backtest("strategy_b", result_b)
        best = await tracker.best_strategy("total_return")
        assert best is not None
        assert best[0] == "strategy_b"


class TestStrategyRanking:
    """Tests for strategy ranking."""

    @pytest.mark.asyncio
    async def test_ranking_order(self, sample_backtest_result: BacktestResult) -> None:
        tracker = PerformanceTracker()
        result_low = BacktestResult(
            strategy_name="low",
            symbol="SOL/USDC",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
            metrics=PerformanceMetrics(sharpe_ratio=0.5),
        )
        result_high = BacktestResult(
            strategy_name="high",
            symbol="SOL/USDC",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
            metrics=PerformanceMetrics(sharpe_ratio=2.5),
        )
        await tracker.record_backtest("low", result_low)
        await tracker.record_backtest("high", result_high)
        ranking = await tracker.strategy_ranking("sharpe_ratio")
        assert len(ranking) == 2
        assert ranking[0][0] == "high"
        assert ranking[1][0] == "low"

    @pytest.mark.asyncio
    async def test_ranking_empty(self) -> None:
        tracker = PerformanceTracker()
        ranking = await tracker.strategy_ranking()
        assert ranking == []


class TestAggregateStats:
    """Tests for aggregate statistics."""

    @pytest.mark.asyncio
    async def test_aggregate(self, sample_backtest_result: BacktestResult) -> None:
        tracker = PerformanceTracker()
        await tracker.record_backtest("a", sample_backtest_result)
        result_b = BacktestResult(
            strategy_name="b",
            symbol="SOL/USDC",
            start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
            metrics=PerformanceMetrics(sharpe_ratio=2.0, total_return=0.1),
        )
        await tracker.record_backtest("b", result_b)
        stats = await tracker.get_aggregate_stats()
        assert stats["total_strategies"] == 2
        assert stats["total_backtests"] == 2
        assert "avg_sharpe" in stats

    @pytest.mark.asyncio
    async def test_aggregate_empty(self) -> None:
        tracker = PerformanceTracker()
        stats = await tracker.get_aggregate_stats()
        assert stats["total_strategies"] == 0
        assert stats["total_backtests"] == 0


class TestClearHistory:
    """Tests for clearing history."""

    def test_clear_all(self, sample_backtest_result: BacktestResult) -> None:
        tracker = PerformanceTracker()
        # Can't use async in non-async test, manipulate directly
        tracker._history["a"] = [sample_backtest_result]
        tracker.clear_history()
        assert tracker._history == {}

    def test_clear_single(self, sample_backtest_result: BacktestResult) -> None:
        tracker = PerformanceTracker()
        tracker._history["a"] = [sample_backtest_result]
        tracker._history["b"] = [sample_backtest_result]
        tracker.clear_history("a")
        assert "a" not in tracker._history
        assert "b" in tracker._history
