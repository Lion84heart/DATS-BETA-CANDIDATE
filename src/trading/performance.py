"""DATS — Performance Tracking.

Tracks and compares strategy performance over time with historical
backtest recording and strategy ranking.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from trading.schemas import BacktestResult, PerformanceMetrics

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """Tracks and compares strategy performance over time.

    Maintains an in-memory history of backtest results per strategy.
    Supports comparison tables, best strategy selection, and rankings.
    """

    def __init__(self) -> None:
        self._history: dict[str, list[BacktestResult]] = {}

    async def record_backtest(self, strategy_name: str, result: BacktestResult) -> None:
        """Record a backtest result for a strategy.

        Args:
            strategy_name: Strategy identifier.
            result: BacktestResult to store.
        """
        if strategy_name not in self._history:
            self._history[strategy_name] = []
        self._history[strategy_name].append(result)
        logger.debug(
            "Recorded backtest for %s: return=%.4f, sharpe=%.4f",
            strategy_name,
            result.total_return,
            result.sharpe_ratio,
        )

    async def get_history(self, strategy_name: str) -> list[BacktestResult]:
        """Get backtest history for a strategy.

        Args:
            strategy_name: Strategy identifier.

        Returns:
            List of BacktestResult objects.
        """
        return list(self._history.get(strategy_name, []))

    async def compare_strategies(
        self,
        strategy_names: list[str],
        metrics: list[str] | None = None,
    ) -> pd.DataFrame:
        """Compare multiple strategies across key metrics.

        Args:
            strategy_names: List of strategy names to compare.
            metrics: Optional list of metric names to include.
                     Defaults to all key metrics.

        Returns:
            DataFrame with strategies as rows and metrics as columns.
        """
        if metrics is None:
            metrics = [
                "total_return",
                "sharpe_ratio",
                "max_drawdown",
                "win_rate",
                "profit_factor",
                "num_trades",
                "expectancy",
            ]

        rows: list[dict[str, Any]] = []
        for name in strategy_names:
            history = self._history.get(name, [])
            if not history:
                continue
            # Use the most recent result
            latest = history[-1]
            row: dict[str, Any] = {"strategy": name}
            for metric in metrics:
                row[metric] = round(getattr(latest.metrics, metric, 0.0), 4)
            rows.append(row)

        if not rows:
            return pd.DataFrame(columns=["strategy"] + (metrics or []))

        df = pd.DataFrame(rows)
        df = df.set_index("strategy")
        return df

    async def best_strategy(
        self,
        metric: str = "sharpe_ratio",
    ) -> tuple[str, PerformanceMetrics] | None:
        """Find the best strategy by a given metric.

        Args:
            metric: Metric name to optimize.

        Returns:
            Tuple of (strategy_name, metrics) or None if no data.
        """
        best_name: str | None = None
        best_value: float = float("-inf")
        best_metrics: PerformanceMetrics | None = None

        for name, history in self._history.items():
            if not history:
                continue
            latest = history[-1]
            value = getattr(latest.metrics, metric, float("-inf"))
            if value > best_value:
                best_value = value
                best_name = name
                best_metrics = latest.metrics

        if best_name is None or best_metrics is None:
            return None
        return (best_name, best_metrics)

    async def strategy_ranking(
        self,
        metric: str = "sharpe_ratio",
    ) -> list[tuple[str, PerformanceMetrics]]:
        """Rank all strategies by a given metric.

        Args:
            metric: Metric name to rank by.

        Returns:
            List of (strategy_name, metrics) sorted descending by metric.
        """
        scored: list[tuple[str, PerformanceMetrics, float]] = []
        for name, history in self._history.items():
            if not history:
                continue
            latest = history[-1]
            value = getattr(latest.metrics, metric, float("-inf"))
            scored.append((name, latest.metrics, value))

        scored.sort(key=lambda x: x[2], reverse=True)
        return [(name, metrics) for name, metrics, _value in scored]

    async def get_aggregate_stats(self) -> dict[str, Any]:
        """Get aggregate statistics across all strategies.

        Returns:
            Dict with total strategies, total backtests, and average metrics.
        """
        total_backtests = sum(len(h) for h in self._history.values())
        total_strategies = len(self._history)

        all_metrics: list[PerformanceMetrics] = []
        for history in self._history.values():
            if history:
                all_metrics.append(history[-1].metrics)

        if not all_metrics:
            return {
                "total_strategies": total_strategies,
                "total_backtests": total_backtests,
            }

        return {
            "total_strategies": total_strategies,
            "total_backtests": total_backtests,
            "avg_sharpe": sum(m.sharpe_ratio for m in all_metrics) / len(all_metrics),
            "avg_return": sum(m.total_return for m in all_metrics) / len(all_metrics),
            "avg_max_drawdown": sum(m.max_drawdown for m in all_metrics) / len(all_metrics),
            "avg_win_rate": sum(m.win_rate for m in all_metrics) / len(all_metrics),
        }

    def clear_history(self, strategy_name: str | None = None) -> None:
        """Clear history for a specific strategy or all strategies.

        Args:
            strategy_name: Strategy to clear, or None to clear all.
        """
        if strategy_name is None:
            self._history.clear()
        elif strategy_name in self._history:
            del self._history[strategy_name]
