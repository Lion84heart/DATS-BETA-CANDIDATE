"""Composes one ``mission_config.ExperimentConfig`` into an actual
backtest run — strategy subset + fusion method + confidence gate +
trade-management preset — entirely by calling existing, already-tested
machinery (``backtesting.engine.default_strategies``,
``execution_intelligence.managed_backtest.run_managed_backtest``).
Nothing here re-implements a backtest loop.
"""

from __future__ import annotations

from typing import Any

from backtesting.data import HistoricalBar
from backtesting.engine import BacktestRunConfig, default_strategies
from execution_intelligence.managed_backtest import run_managed_backtest
from research.mission_config import FUSION_METHODS, STRATEGY_SUBSETS, ExperimentConfig, trade_management_presets


def _strategies_for(subset_name: str):
    names = STRATEGY_SUBSETS[subset_name]
    all_strategies = default_strategies()
    if names is None:
        return all_strategies
    return [s for s in all_strategies if s.name in names]


async def run_experiment(
    bars: list[HistoricalBar], symbol: str, experiment: ExperimentConfig,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one experiment and return ``(metrics_dict, extra)``.

    ``MajorityVoteFusion`` (the only non-None fusion option) is stateless
    — its ``combine()`` never mutates ``self`` — so sharing the one
    instance ``FUSION_METHODS`` holds across every experiment run is safe.
    """
    strategies = _strategies_for(experiment.strategy_subset)
    fusion = FUSION_METHODS[experiment.fusion_method]
    managed = trade_management_presets()[experiment.trade_management]
    managed.min_confidence = experiment.confidence_threshold

    config = BacktestRunConfig(symbol=symbol)
    report, extra = await run_managed_backtest(bars, config, managed, strategies=strategies, fusion=fusion)

    from dataclasses import asdict
    metrics = asdict(report.portfolio_metrics)
    metrics["num_bars"] = report.num_bars
    return metrics, extra
