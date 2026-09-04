"""Phase 2 quantitative research study: Market Regime Engine.

Orchestrates, over the frozen Strategy Engine / Decision Fusion /
BacktestEngine (all used strictly read-only via the Sprint 6 pattern):

  1. Regime detection over real synthetic OHLCV (research.regime).
  2. Empirically-derived, out-of-sample regime->strategy routing
     weights (research.regime_router), fit on one seed series.
  3. A head-to-head comparison grid — the frozen, unmodified
     BacktestEngine (static, live DecisionFusion) vs. the regime-aware
     router (research.regime_backtest) — on a *different* seed series
     from the one weights were fit on, so the comparison is genuinely
     out-of-sample, not fit-then-graded-on-the-same-data.

Nothing here modifies trading/strategies/*, intelligence/fusion.py,
intelligence/engine.py, trading/execution/*, or backtesting/engine.py.
"""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

from backtesting.engine import BacktestEngine, BacktestRunConfig, default_strategies
from research.regime import REGIMES, detect_regimes, time_in_regime_pct
from research.regime_backtest import run_regime_aware_backtest
from research.regime_router import (
    average_edge_across_symbols,
    collect_strategy_signals,
    compute_regime_edge_scores,
    edge_scores_as_json,
    edge_scores_to_weights,
)
from research.study import PRIMARY_TIMEFRAME, SYMBOLS, TIMEFRAMES, _bars_for

FIT_BARS_PER_SYMBOL = 2000  # weight-fitting series length, primary timeframe only
EVAL_BARS_PER_RUN = 1000    # comparison-grid series length, every (symbol, timeframe)
FIT_TAG = "regime-fit"      # distinct seed series from the eval grid -> out-of-sample weights
EVAL_TAG = "regime-eval"


def _metrics_dict(report) -> dict[str, Any]:  # noqa: ANN001 - BacktestReport, avoid import cycle
    return asdict(report.portfolio_metrics)


def fit_regime_routing_weights() -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    """Derive regime -> strategy weight vectors from real backtested
    signal precision, averaged across all 8 symbols at the primary
    (1D) timeframe, on the ``regime-fit`` seed series (distinct from
    the ``regime-eval`` series the comparison grid uses).
    """
    strategies = default_strategies()
    per_symbol_edge: list[dict[str, dict[str, float]]] = []
    time_in_regime_by_symbol: dict[str, dict[str, float]] = {}

    for symbol in SYMBOLS:
        bars = _bars_for(symbol, PRIMARY_TIMEFRAME, FIT_BARS_PER_SYMBOL, tag=FIT_TAG)
        regimes = detect_regimes(bars)
        predictions = collect_strategy_signals(bars, strategies)
        edge = compute_regime_edge_scores(bars, regimes, predictions)
        per_symbol_edge.append(edge)
        time_in_regime_by_symbol[symbol] = time_in_regime_pct(regimes)

    avg_edge = average_edge_across_symbols(per_symbol_edge)
    weights_by_regime = edge_scores_to_weights(avg_edge)

    fit_metadata = {
        "fit_bars_per_symbol": FIT_BARS_PER_SYMBOL,
        "fit_tag": FIT_TAG,
        "avg_edge_by_regime": edge_scores_as_json(avg_edge),
        "time_in_regime_by_symbol_pct": time_in_regime_by_symbol,
    }
    return weights_by_regime, fit_metadata


async def run_comparison_grid(weights_by_regime: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    """For every (symbol, timeframe): the frozen static BacktestEngine
    (live DecisionFusion) vs. the regime-aware router, on the identical,
    out-of-sample ``regime-eval`` bar series.
    """
    rows: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            bars = _bars_for(symbol, timeframe, EVAL_BARS_PER_RUN, tag=EVAL_TAG)
            config = BacktestRunConfig(symbol=symbol)

            static_engine = BacktestEngine()  # frozen, unmodified: default strategies + live DecisionFusion
            static_report = await static_engine.run(bars, config)
            rows.append({
                "symbol": symbol, "timeframe": timeframe, "variant": "static_decision_fusion",
                "num_bars": static_report.num_bars, **_metrics_dict(static_report),
            })

            regime_report, regime_time_pct = await run_regime_aware_backtest(bars, config, weights_by_regime)
            rows.append({
                "symbol": symbol, "timeframe": timeframe, "variant": "regime_aware_routing",
                "num_bars": regime_report.num_bars, "time_in_regime_pct": regime_time_pct,
                **_metrics_dict(regime_report),
            })
    return rows


async def run_full_regime_study() -> dict[str, Any]:
    """Run the complete Phase 2 study and return the full results bundle."""
    started_at = time.time()

    weights_by_regime, fit_metadata = fit_regime_routing_weights()
    grid_rows = await run_comparison_grid(weights_by_regime)

    return {
        "started_at": started_at,
        "completed_at": time.time(),
        "symbols": SYMBOLS,
        "timeframes": TIMEFRAMES,
        "regimes": list(REGIMES),
        "eval_bars_per_run": EVAL_BARS_PER_RUN,
        "eval_tag": EVAL_TAG,
        "regime_routing_weights": weights_by_regime,
        "fit_metadata": fit_metadata,
        "comparison_grid_results": grid_rows,
    }
