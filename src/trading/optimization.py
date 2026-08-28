"""DATS — Parameter Optimization.

Grid search, random search, and walk-forward optimization for strategy parameters.
"""

from __future__ import annotations

import itertools
import logging
import random
from typing import Any

import pandas as pd

from trading.backtest import BacktestEngine
from trading.base_strategy import BaseStrategy
from trading.schemas import PerformanceMetrics, StrategyConfig

logger = logging.getLogger(__name__)


class ParameterOptimizer:
    """Grid search + random search for strategy parameter optimization."""

    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission_rate: float = 0.001,
    ) -> None:
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate

    async def grid_search(
        self,
        strategy_class: type[BaseStrategy],
        ohlcv_df: pd.DataFrame,
        parameter_grid: dict[str, list[float]],
        metric: str = "sharpe_ratio",
        symbol: str = "TEST/USDC",
    ) -> list[tuple[dict[str, float], PerformanceMetrics]]:
        """Grid search over all parameter combinations.

        Args:
            strategy_class: Strategy class to optimize.
            ohlcv_df: OHLCV DataFrame for backtesting.
            parameter_grid: Dict of parameter name -> list of values to try.
            metric: Metric to optimize (e.g. 'sharpe_ratio', 'total_return').
            symbol: Trading symbol for the strategy config.

        Returns:
            List of (parameters, metrics) tuples sorted by metric descending.
        """
        if not parameter_grid:
            return []

        keys = sorted(parameter_grid.keys())
        values = [parameter_grid[k] for k in keys]
        combinations = list(itertools.product(*values))

        logger.info(
            "Grid search: %d parameter combinations over %s",
            len(combinations),
            keys,
        )

        results: list[tuple[dict[str, float], PerformanceMetrics]] = []
        engine = BacktestEngine(
            initial_capital=self.initial_capital,
            commission_rate=self.commission_rate,
        )

        for combo in combinations:
            params = dict(zip(keys, combo))
            config = StrategyConfig(
                strategy_type=strategy_class.strategy_type,
                symbol=symbol,
                parameters=params,
            )
            strategy = strategy_class(config)

            try:
                result = engine.run(strategy, ohlcv_df)
                results.append((params, result.metrics))
            except Exception as exc:
                logger.warning("Backtest failed for params %s: %s", params, exc)
                continue

        # Sort by metric descending
        results.sort(key=lambda x: getattr(x[1], metric, float("-inf")), reverse=True)
        return results

    async def random_search(
        self,
        strategy_class: type[BaseStrategy],
        ohlcv_df: pd.DataFrame,
        n_iterations: int = 100,
        metric: str = "sharpe_ratio",
        symbol: str = "TEST/USDC",
    ) -> list[tuple[dict[str, float], PerformanceMetrics]]:
        """Random search within parameter bounds.

        Args:
            strategy_class: Strategy class to optimize.
            ohlcv_df: OHLCV DataFrame for backtesting.
            n_iterations: Number of random parameter sets to try.
            metric: Metric to optimize.
            symbol: Trading symbol.

        Returns:
            List of (parameters, metrics) tuples sorted by metric descending.
        """
        # Get parameter bounds from a dummy instance
        dummy_config = StrategyConfig(
            strategy_type=strategy_class.strategy_type,
            symbol=symbol,
        )
        dummy = strategy_class(dummy_config)
        bounds = dummy.parameter_bounds()

        if not bounds:
            return []

        logger.info(
            "Random search: %d iterations over %s", n_iterations, sorted(bounds.keys())
        )

        results: list[tuple[dict[str, float], PerformanceMetrics]] = []
        engine = BacktestEngine(
            initial_capital=self.initial_capital,
            commission_rate=self.commission_rate,
        )

        keys = sorted(bounds.keys())
        for _i in range(n_iterations):
            params: dict[str, float] = {}
            for key in keys:
                min_val, max_val = bounds[key]
                # Handle integer parameters (periods)
                if key in ("fast_ema", "slow_ema", "bb_period", "rsi_period",
                           "macd_fast", "macd_slow", "macd_signal", "lookback",
                           "zscore_window"):
                    params[key] = float(random.randint(int(min_val), int(max_val)))
                else:
                    params[key] = random.uniform(min_val, max_val)

            config = StrategyConfig(
                strategy_type=strategy_class.strategy_type,
                symbol=symbol,
                parameters=params,
            )
            strategy = strategy_class(config)

            try:
                result = engine.run(strategy, ohlcv_df)
                results.append((params, result.metrics))
            except Exception as exc:
                logger.debug("Backtest failed for params %s: %s", params, exc)
                continue

        results.sort(key=lambda x: getattr(x[1], metric, float("-inf")), reverse=True)
        return results

    async def walk_forward_optimization(
        self,
        strategy_class: type[BaseStrategy],
        ohlcv_df: pd.DataFrame,
        train_size: int,
        test_size: int,
        n_splits: int = 5,
        n_random_iterations: int = 20,
        metric: str = "sharpe_ratio",
        symbol: str = "TEST/USDC",
    ) -> list[dict[str, Any]]:
        """Walk-forward optimization.

        For each split:
        1. Train on [start:start+train_size] — find best params via random search.
        2. Test on [start+train_size:start+train_size+test_size].
        3. Move window forward by test_size.

        Args:
            strategy_class: Strategy class to optimize.
            ohlcv_df: Full OHLCV DataFrame.
            train_size: Number of bars for training.
            test_size: Number of bars for testing.
            n_splits: Maximum number of walk-forward splits.
            n_random_iterations: Random search iterations per training window.
            metric: Metric to optimize.
            symbol: Trading symbol.

        Returns:
            List of per-split results with train/test params and metrics.
        """
        results: list[dict[str, Any]] = []
        engine = BacktestEngine(
            initial_capital=self.initial_capital,
            commission_rate=self.commission_rate,
        )

        split_idx = 0
        start = 0

        while split_idx < n_splits and start + train_size + test_size <= len(ohlcv_df):
            train_df = ohlcv_df.iloc[start : start + train_size]
            test_df = ohlcv_df.iloc[start + train_size : start + train_size + test_size]

            # Optimize on training data
            train_results = await self.random_search(
                strategy_class=strategy_class,
                ohlcv_df=train_df,
                n_iterations=n_random_iterations,
                metric=metric,
                symbol=symbol,
            )

            if not train_results:
                start += test_size
                split_idx += 1
                continue

            best_params, train_metrics = train_results[0]

            # Test on out-of-sample data
            config = StrategyConfig(
                strategy_type=strategy_class.strategy_type,
                symbol=symbol,
                parameters=best_params,
            )
            strategy = strategy_class(config)
            test_result = engine.run(strategy, test_df)

            results.append({
                "split": split_idx,
                "train_start": start,
                "train_end": start + train_size,
                "test_start": start + train_size,
                "test_end": start + train_size + test_size,
                "best_params": best_params,
                "train_metric": getattr(train_metrics, metric),
                "test_metric": getattr(test_result.metrics, metric),
                "test_metrics": test_result.metrics,
                "train_results_count": len(train_results),
            })

            logger.info(
                "Walk-forward split %d: train_%s=%.4f, test_%s=%.4f, params=%s",
                split_idx,
                metric,
                getattr(train_metrics, metric),
                metric,
                getattr(test_result.metrics, metric),
                best_params,
            )

            start += test_size
            split_idx += 1

        return results
