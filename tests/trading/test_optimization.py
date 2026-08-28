"""Tests for parameter optimization."""

from __future__ import annotations

import pandas as pd
import pytest

from src.trading.optimization import ParameterOptimizer
from src.trading.schemas import StrategyConfig, StrategyType
from src.trading.strategies.trend_following import TrendFollowingStrategy
from tests.trading.conftest import MockStrategy


class TestParameterOptimizerInit:
    """Tests for optimizer initialization."""

    def test_default_config(self) -> None:
        opt = ParameterOptimizer()
        assert opt.initial_capital == 10000.0
        assert opt.commission_rate == 0.001

    def test_custom_config(self) -> None:
        opt = ParameterOptimizer(initial_capital=50000.0, commission_rate=0.002)
        assert opt.initial_capital == 50000.0
        assert opt.commission_rate == 0.002


class TestGridSearch:
    """Tests for grid search optimization."""

    @pytest.mark.asyncio
    async def test_grid_search_basic(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        opt = ParameterOptimizer()
        grid = {"fast_ema": [5.0, 10.0], "slow_ema": [15.0, 20.0]}
        results = await opt.grid_search(
            strategy_class=TrendFollowingStrategy,
            ohlcv_df=sample_ohlcv_fast,
            parameter_grid=grid,
            metric="sharpe_ratio",
            symbol="SOL/USDC",
        )
        assert len(results) == 4  # 2x2 combinations
        # Results should be sorted by sharpe_ratio descending
        if len(results) > 1:
            sharpe_values = [r[1].sharpe_ratio for r in results]
            assert sharpe_values == sorted(sharpe_values, reverse=True)

    @pytest.mark.asyncio
    async def test_grid_search_empty_grid(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        opt = ParameterOptimizer()
        results = await opt.grid_search(
            strategy_class=TrendFollowingStrategy,
            ohlcv_df=sample_ohlcv_fast,
            parameter_grid={},
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_grid_search_single_param(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        opt = ParameterOptimizer()
        grid = {"adx_threshold": [20.0, 25.0, 30.0]}
        results = await opt.grid_search(
            strategy_class=TrendFollowingStrategy,
            ohlcv_df=sample_ohlcv_fast,
            parameter_grid=grid,
        )
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_grid_search_returns_parameters(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        opt = ParameterOptimizer()
        grid = {"fast_ema": [5.0, 10.0]}
        results = await opt.grid_search(
            strategy_class=TrendFollowingStrategy,
            ohlcv_df=sample_ohlcv_fast,
            parameter_grid=grid,
        )
        assert len(results) > 0
        params, metrics = results[0]
        assert "fast_ema" in params
        assert hasattr(metrics, "sharpe_ratio")


class TestRandomSearch:
    """Tests for random search optimization."""

    @pytest.mark.asyncio
    async def test_random_search_basic(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        opt = ParameterOptimizer()
        results = await opt.random_search(
            strategy_class=TrendFollowingStrategy,
            ohlcv_df=sample_ohlcv_fast,
            n_iterations=3,
            metric="sharpe_ratio",
        )
        assert len(results) <= 3
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_random_search_sorted(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        opt = ParameterOptimizer()
        results = await opt.random_search(
            strategy_class=TrendFollowingStrategy,
            ohlcv_df=sample_ohlcv_fast,
            n_iterations=3,
            metric="sharpe_ratio",
        )
        if len(results) > 1:
            sharpe_values = [r[1].sharpe_ratio for r in results]
            assert sharpe_values == sorted(sharpe_values, reverse=True)

    @pytest.mark.asyncio
    async def test_random_search_zero_iterations(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        opt = ParameterOptimizer()
        results = await opt.random_search(
            strategy_class=TrendFollowingStrategy,
            ohlcv_df=sample_ohlcv_fast,
            n_iterations=0,
        )
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_random_search_returns_valid_params(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        opt = ParameterOptimizer()
        results = await opt.random_search(
            strategy_class=TrendFollowingStrategy,
            ohlcv_df=sample_ohlcv_fast,
            n_iterations=3,
        )
        if results:
            params, metrics = results[0]
            assert isinstance(params, dict)
            assert hasattr(metrics, "total_return")
            assert hasattr(metrics, "sharpe_ratio")


class TestWalkForwardOptimization:
    """Tests for walk-forward optimization."""

    @pytest.mark.asyncio
    async def test_walk_forward_basic(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        opt = ParameterOptimizer()
        results = await opt.walk_forward_optimization(
            strategy_class=TrendFollowingStrategy,
            ohlcv_df=sample_ohlcv_fast,
            train_size=80,
            test_size=40,
            n_splits=2,
            n_random_iterations=2,
        )
        assert isinstance(results, list)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_walk_forward_split_structure(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        opt = ParameterOptimizer()
        results = await opt.walk_forward_optimization(
            strategy_class=TrendFollowingStrategy,
            ohlcv_df=sample_ohlcv_fast,
            train_size=80,
            test_size=40,
            n_splits=2,
            n_random_iterations=2,
        )
        for result in results:
            assert "split" in result
            assert "best_params" in result
            assert "train_metric" in result
            assert "test_metric" in result
            assert isinstance(result["best_params"], dict)

    @pytest.mark.asyncio
    async def test_walk_forward_with_mock_strategy(self, sample_ohlcv_fast: pd.DataFrame) -> None:
        opt = ParameterOptimizer()
        results = await opt.walk_forward_optimization(
            strategy_class=MockStrategy,
            ohlcv_df=sample_ohlcv_fast,
            train_size=80,
            test_size=40,
            n_splits=2,
            n_random_iterations=2,
        )
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_walk_forward_insufficient_data(self) -> None:
        opt = ParameterOptimizer()
        df = pd.DataFrame({
            "open": [100.0] * 50,
            "high": [101.0] * 50,
            "low": [99.0] * 50,
            "close": [100.0] * 50,
            "volume": [1000.0] * 50,
        })
        results = await opt.walk_forward_optimization(
            strategy_class=TrendFollowingStrategy,
            ohlcv_df=df,
            train_size=100,
            test_size=50,
            n_splits=2,
        )
        assert results == []
