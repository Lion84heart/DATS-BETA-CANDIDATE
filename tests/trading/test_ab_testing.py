"""Tests for the A/B testing framework."""

from __future__ import annotations

import pandas as pd
import pytest

from src.trading.ab_testing import ABTestFramework
from src.trading.schemas import (
    ABTest,
    BacktestResult,
    PerformanceMetrics,
    StrategyConfig,
    StrategyType,
)
from src.trading.strategies.trend_following import TrendFollowingStrategy
from src.trading.strategies.mean_reversion import MeanReversionStrategy
from tests.trading.conftest import MockStrategy
from datetime import datetime, timezone


class TestABTestFrameworkInit:
    """Tests for framework initialization."""

    def test_default_config(self) -> None:
        framework = ABTestFramework()
        assert framework.initial_capital == 10000.0
        assert framework.commission_rate == 0.001

    def test_custom_config(self) -> None:
        framework = ABTestFramework(initial_capital=50000.0, commission_rate=0.002)
        assert framework.initial_capital == 50000.0


class TestCreateTest:
    """Tests for creating A/B test configurations."""

    @pytest.mark.asyncio
    async def test_create_test(self, sample_ab_test: ABTest) -> None:
        assert sample_ab_test.name == "trend_vs_mean_rev"
        assert sample_ab_test.strategy_a_name == "trend_following"
        assert sample_ab_test.strategy_b_name == "mean_reversion"
        assert sample_ab_test.confidence_level == 0.95
        assert sample_ab_test.status == "pending"

    @pytest.mark.asyncio
    async def test_create_test_custom_confidence(self) -> None:
        framework = ABTestFramework()
        config_a = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        config_b = StrategyConfig(
            strategy_type=StrategyType.MEAN_REVERSION,
            symbol="SOL/USDC",
        )
        strategy_a = TrendFollowingStrategy(config_a)
        strategy_b = MeanReversionStrategy(config_b)
        test = await framework.create_test(
            "custom_test", strategy_a, strategy_b, pd.DataFrame(),
            confidence_level=0.99,
        )
        assert test.confidence_level == 0.99


class TestRunTest:
    """Tests for running A/B tests."""

    @pytest.mark.asyncio
    async def test_run_test(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        framework = ABTestFramework()
        config_a = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        config_b = StrategyConfig(
            strategy_type=StrategyType.MEAN_REVERSION,
            symbol="SOL/USDC",
        )
        strategy_a = TrendFollowingStrategy(config_a)
        strategy_b = MeanReversionStrategy(config_b)
        test = await framework.create_test("test1", strategy_a, strategy_b, sample_ohlcv_fast)
        result = await framework.run_test(test, sample_ohlcv_fast, strategy_a, strategy_b)
        assert result is not None
        assert result.test_name == "test1"
        assert result.winner in ("A", "B", "tie")
        assert 0.0 <= result.p_value <= 1.0
        assert result.confidence == 0.95
        assert len(result.recommendation) > 0

    @pytest.mark.asyncio
    async def test_result_has_metrics(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        framework = ABTestFramework()
        config_a = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        config_b = StrategyConfig(
            strategy_type=StrategyType.MEAN_REVERSION,
            symbol="SOL/USDC",
        )
        strategy_a = TrendFollowingStrategy(config_a)
        strategy_b = MeanReversionStrategy(config_b)
        test = await framework.create_test("test2", strategy_a, strategy_b, sample_ohlcv_fast)
        result = await framework.run_test(test, sample_ohlcv_fast, strategy_a, strategy_b)
        assert result.strategy_a_metrics is not None
        assert result.strategy_b_metrics is not None
        assert hasattr(result.strategy_a_metrics, "sharpe_ratio")
        assert hasattr(result.strategy_b_metrics, "sharpe_ratio")

    @pytest.mark.asyncio
    async def test_result_has_recommendation(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        framework = ABTestFramework()
        config_a = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        config_b = StrategyConfig(
            strategy_type=StrategyType.MEAN_REVERSION,
            symbol="SOL/USDC",
        )
        strategy_a = TrendFollowingStrategy(config_a)
        strategy_b = MeanReversionStrategy(config_b)
        test = await framework.create_test("test3", strategy_a, strategy_b, sample_ohlcv_fast)
        result = await framework.run_test(test, sample_ohlcv_fast, strategy_a, strategy_b)
        assert len(result.recommendation) > 0
        assert isinstance(result.recommendation, str)

    @pytest.mark.asyncio
    async def test_p_value_in_range(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        framework = ABTestFramework()
        config_a = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        config_b = StrategyConfig(
            strategy_type=StrategyType.MEAN_REVERSION,
            symbol="SOL/USDC",
        )
        strategy_a = TrendFollowingStrategy(config_a)
        strategy_b = MeanReversionStrategy(config_b)
        test = await framework.create_test("test4", strategy_a, strategy_b, sample_ohlcv_fast)
        result = await framework.run_test(test, sample_ohlcv_fast, strategy_a, strategy_b)
        assert 0.0 <= result.p_value <= 1.0

    @pytest.mark.asyncio
    async def test_winner_is_valid(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        framework = ABTestFramework()
        config_a = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        config_b = StrategyConfig(
            strategy_type=StrategyType.MEAN_REVERSION,
            symbol="SOL/USDC",
        )
        strategy_a = TrendFollowingStrategy(config_a)
        strategy_b = MeanReversionStrategy(config_b)
        test = await framework.create_test("test5", strategy_a, strategy_b, sample_ohlcv_fast)
        result = await framework.run_test(test, sample_ohlcv_fast, strategy_a, strategy_b)
        assert result.winner in ("A", "B", "tie")

    @pytest.mark.asyncio
    async def test_with_same_strategy(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        """Test with identical strategies should result in a tie."""
        framework = ABTestFramework()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy_a = TrendFollowingStrategy(config)
        strategy_b = TrendFollowingStrategy(config)
        test = await framework.create_test("same", strategy_a, strategy_b, sample_ohlcv_fast)
        result = await framework.run_test(test, sample_ohlcv_fast, strategy_a, strategy_b)
        assert result.winner == "tie"

    @pytest.mark.asyncio
    async def test_run_test_raises_without_strategies(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        framework = ABTestFramework()
        test = ABTest(name="bad", strategy_a_name="a", strategy_b_name="b")
        with pytest.raises(ValueError, match="strategy_a is required"):
            await framework.run_test(test, sample_ohlcv_fast)


class TestCompositeScore:
    """Tests for composite score computation."""

    def test_score_positive_metrics(self) -> None:
        framework = ABTestFramework()
        metrics = PerformanceMetrics(
            sharpe_ratio=2.0,
            total_return=0.1,
            win_rate=0.6,
            calmar_ratio=5.0,
            expectancy=0.05,
        )
        score = framework._compute_composite_score(metrics)
        assert score > 0

    def test_score_zero_metrics(self) -> None:
        framework = ABTestFramework()
        metrics = PerformanceMetrics()
        score = framework._compute_composite_score(metrics)
        assert score == 0.0

    def test_score_higher_is_better(self) -> None:
        framework = ABTestFramework()
        low = PerformanceMetrics(sharpe_ratio=0.5, total_return=0.01)
        high = PerformanceMetrics(sharpe_ratio=3.0, total_return=0.3)
        assert framework._compute_composite_score(high) > framework._compute_composite_score(low)


class TestCompareMultiple:
    """Tests for comparing multiple strategies."""

    @pytest.mark.asyncio
    async def test_compare_multiple(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        framework = ABTestFramework()
        config_a = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        config_b = StrategyConfig(
            strategy_type=StrategyType.MEAN_REVERSION,
            symbol="SOL/USDC",
        )
        strategy_a = TrendFollowingStrategy(config_a)
        strategy_b = MeanReversionStrategy(config_b)
        df = await framework.compare_multiple(
            [strategy_a, strategy_b],
            sample_ohlcv_fast,
        )
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1  # One pairwise comparison for 2 strategies
        assert "strategy_a" in df.columns
        assert "strategy_b" in df.columns
        assert "winner" in df.columns

    @pytest.mark.asyncio
    async def test_compare_multiple_three_strategies(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        framework = ABTestFramework()
        strategies = [
            TrendFollowingStrategy(StrategyConfig(strategy_type=StrategyType.TREND_FOLLOWING, symbol="SOL/USDC")),
            MeanReversionStrategy(StrategyConfig(strategy_type=StrategyType.MEAN_REVERSION, symbol="SOL/USDC")),
            MockStrategy(StrategyConfig(strategy_type=StrategyType.TREND_FOLLOWING, symbol="SOL/USDC")),
        ]
        df = await framework.compare_multiple(strategies, sample_ohlcv_fast)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3  # 3 pairwise comparisons for 3 strategies
