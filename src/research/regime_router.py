"""Phase 2 — Regime-conditional strategy routing weights (research-only).

Derives, for each of the five market regimes, a per-strategy weight
vector from real backtested evidence: how accurate each (frozen,
unmodified) strategy's BUY/SELL signals actually were *specifically
during bars of that regime*, using the same forward-return UP/DOWN/FLAT
convention the frozen ``backtesting.confusion.compute_confusion_matrix``
already defines and computes — reused unmodified, not reimplemented.

No new indicator or strategy is introduced anywhere in this module:
every signal comes from calling the existing ``BaseStrategy.generate_signal``
the same way ``backtesting.engine.BacktestEngine`` already does.
"""

from __future__ import annotations

import statistics
from typing import Any

import pandas as pd

from backtesting.confusion import ConfusionMatrix, compute_confusion_matrix
from backtesting.data import HistoricalBar
from research.regime import REGIMES
from trading.base_strategy import BaseStrategy

_MAX_WINDOW = 200  # mirrors backtesting.engine.BacktestEngine's rolling window cap
_NOT_IN_REGIME = "N/A"  # sentinel: excluded from compute_confusion_matrix's tabulation


def collect_strategy_signals(
    bars: list[HistoricalBar], strategies: list[BaseStrategy]
) -> dict[str, list[str]]:
    """Per-bar BUY/SELL/HOLD prediction for every strategy.

    Read-only signal collection — no broker, no trade simulation. Uses
    the identical rolling-window/DataFrame construction
    ``BacktestEngine.run()`` uses, so the signals collected here are
    exactly what a real backtest would see at each bar.
    """
    window: list[dict[str, float]] = []
    predictions: dict[str, list[str]] = {s.name: [] for s in strategies}
    for bar in bars:
        window.append(
            {"timestamp": bar.timestamp, "open": bar.open, "high": bar.high,
             "low": bar.low, "close": bar.close, "volume": bar.volume}
        )
        if len(window) > _MAX_WINDOW:
            window.pop(0)
        df = pd.DataFrame(window)
        for strategy in strategies:
            try:
                signal = strategy.generate_signal(df, features={})
            except Exception:
                signal = None
            predictions[strategy.name].append(signal.direction.value if signal is not None else "HOLD")
    return predictions


def _strategy_regime_edge(cm: ConfusionMatrix) -> float:
    """A single 'edge' score (0-100) for one (strategy, regime) pair:
    the support-weighted average of BUY precision and SELL precision —
    i.e. how often that strategy's directional calls were actually right
    during bars of this regime. HOLD precision is excluded: a strategy
    that mostly holds during a regime isn't showing an edge, just
    caution, which shouldn't inflate its routing weight there.
    """
    buy_support = cm.support.get("BUY", 0)
    sell_support = cm.support.get("SELL", 0)
    total = buy_support + sell_support
    if total == 0:
        return 50.0  # no directional calls in this regime -> neutral (coin-flip scale)
    return (
        cm.precision_pct.get("BUY", 0.0) * buy_support
        + cm.precision_pct.get("SELL", 0.0) * sell_support
    ) / total


def compute_regime_edge_scores(
    bars: list[HistoricalBar],
    regimes: list[str],
    predictions_by_strategy: dict[str, list[str]],
    horizon: int = 5,
    threshold_pct: float = 0.1,
) -> dict[str, dict[str, float]]:
    """For every (regime, strategy) pair, the edge score defined above.

    Reuses the frozen ``compute_confusion_matrix`` unmodified: bars
    outside the target regime are masked to a sentinel prediction value
    that isn't one of BUY/SELL/HOLD, so they're silently excluded from
    that regime's tabulation while ``closes`` stays fully intact (the
    function needs contiguous indices to look ``horizon`` bars ahead).
    """
    closes = [b.close for b in bars]
    edge_by_regime: dict[str, dict[str, float]] = {r: {} for r in REGIMES}
    for regime in REGIMES:
        for name, preds in predictions_by_strategy.items():
            masked = [p if regimes[i] == regime else _NOT_IN_REGIME for i, p in enumerate(preds)]
            cm = compute_confusion_matrix(masked, closes, horizon=horizon, threshold_pct=threshold_pct)
            edge_by_regime[regime][name] = _strategy_regime_edge(cm)
    return edge_by_regime


def average_edge_across_symbols(
    per_symbol_edge: list[dict[str, dict[str, float]]],
) -> dict[str, dict[str, float]]:
    """Average per-(regime, strategy) edge scores across multiple symbols'
    independent studies, for one shared, more robust routing table."""
    strategy_names = list(per_symbol_edge[0][REGIMES[0]].keys())
    avg: dict[str, dict[str, float]] = {r: {} for r in REGIMES}
    for regime in REGIMES:
        for name in strategy_names:
            values = [edge[regime][name] for edge in per_symbol_edge]
            avg[regime][name] = statistics.mean(values)
    return avg


def _weights_from_edge(edge: dict[str, float]) -> dict[str, float]:
    """Same normalize -> rescale-to-mean-1 -> clip[0.3,2.0] -> re-center
    method used for Sprint 6's overall recommended weights, applied here
    per regime. No strategy is ever fully silenced in a regime; the
    floor just means "least useful here," not "excluded."

    A final clamp after re-centering guarantees every weight actually
    stays within [0.3, 2.0]: per-regime samples are noisier than
    Sprint 6's single overall average, and when several strategies get
    floored to 0.3 the re-centering step (which restores mean=1.0) can
    otherwise push the remaining strategies' weights back out past 2.0.
    """
    lo, hi = min(edge.values()), max(edge.values())
    if hi - lo < 1e-9:
        norm = {k: 0.5 for k in edge}
    else:
        norm = {k: (v - lo) / (hi - lo) for k, v in edge.items()}
    mean_norm = statistics.mean(norm.values()) or 1.0
    raw = {k: v / mean_norm for k, v in norm.items()}
    clipped = {k: max(0.3, min(2.0, w)) for k, w in raw.items()}
    mean_clipped = statistics.mean(clipped.values()) or 1.0
    recentered = {k: w / mean_clipped for k, w in clipped.items()}
    return {k: round(max(0.3, min(2.0, w)), 3) for k, w in recentered.items()}


def edge_scores_to_weights(edge_by_regime: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """Turn every regime's edge scores into a routing weight vector."""
    return {regime: _weights_from_edge(edge) for regime, edge in edge_by_regime.items()}


def edge_scores_as_json(edge_by_regime: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Round for clean JSON/report output."""
    return {r: {k: round(v, 2) for k, v in scores.items()} for r, scores in edge_by_regime.items()}
