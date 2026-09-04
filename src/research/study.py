"""Sprint 6 quantitative research study.

Orchestrates large-scale backtests over the frozen Strategy Engine and
Decision Fusion (both used strictly read-only, via the frozen
backtesting.BacktestEngine) to produce:

  - Per-strategy performance, independent of fusion.
  - Decision Fusion vs. every individual strategy.
  - Weighted voting (live DecisionFusion) vs. majority voting
    (research-only MajorityVoteFusion) vs. optimized-weight voting
    (research-only WeightedFusion).
  - Symbol-specific and timeframe-specific performance breakdowns.
  - A recommended per-strategy weight vector, derived from real
    backtested evidence (not asserted).

Every backtest in this module goes through BacktestEngine.run() —
nothing here re-implements signal generation, fusion, or trade
simulation. See research/fusion_variants.py for the two comparison-only
fusion implementations.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import asdict
from typing import Any

from backtesting.data import HistoricalBar, generate_synthetic_ohlcv
from backtesting.engine import BacktestEngine, BacktestRunConfig, default_strategies
from research.fusion_variants import MajorityVoteFusion, WeightedFusion

# Same 8-symbol universe used by live Paper Trading / Sprint 5 backtesting.
SYMBOLS: list[str] = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "AMZN", "META", "AMD"]

# Distinct timeframes, expressed as seconds-per-bar.
TIMEFRAMES: dict[str, float] = {"1H": 3600.0, "1D": 86400.0, "1W": 604800.0}
PRIMARY_TIMEFRAME = "1D"

GRID_BARS = 250          # bars per (symbol, timeframe) run in the main comparison grid
FUSION_COMPARISON_BARS = 500  # bars for the majority/weighted/optimized fusion comparison
LARGE_SCALE_BARS = 5000       # bars for the headline "large-scale" flagship runs
LARGE_SCALE_SYMBOLS = ["AAPL", "TSLA", "NVDA"]

RNG_SEED_BASE = 20260904  # fixed base seed — every run in this study is reproducible


def _seed_for(symbol: str, timeframe: str, tag: str = "") -> int:
    """Deterministic per-(symbol, timeframe) seed so every strategy and
    fusion variant compared for that (symbol, timeframe) sees the exact
    same underlying price path — required for a fair, apples-to-apples
    comparison. ``tag`` differentiates the large-scale runs' own series.
    """
    key = f"{symbol}|{timeframe}|{tag}"
    return (RNG_SEED_BASE + sum(ord(c) for c in key)) % (2**31 - 1)


def _bars_for(symbol: str, timeframe: str, num_bars: int, tag: str = "") -> list[HistoricalBar]:
    return generate_synthetic_ohlcv(
        symbol, num_bars, seed=_seed_for(symbol, timeframe, tag),
        bar_seconds=TIMEFRAMES[timeframe],
    )


def _metrics_dict(report) -> dict[str, Any]:  # noqa: ANN001 - BacktestReport, avoid import cycle in signature
    return asdict(report.portfolio_metrics)


async def run_solo_and_fusion_grid() -> list[dict[str, Any]]:
    """For every (symbol, timeframe): backtest each of the 8 strategies
    alone, plus the live DecisionFusion (all 8 combined). Every run for
    a given (symbol, timeframe) replays the identical bar series.

    Returns:
        Flat list of result rows: symbol, timeframe, variant
        ('strategy:<name>' or 'fusion:decision_fusion'), and metrics.
    """
    rows: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            bars = _bars_for(symbol, timeframe, GRID_BARS)
            config = BacktestRunConfig(symbol=symbol)

            # Each strategy alone.
            for strategy in default_strategies():
                engine = BacktestEngine(strategies=[strategy])  # default (live) DecisionFusion; n=1 so it's a pass-through on direction
                report = await engine.run(bars, config)
                rows.append({
                    "symbol": symbol, "timeframe": timeframe, "variant": f"strategy:{strategy.name}",
                    "num_bars": report.num_bars, **_metrics_dict(report),
                })

            # All 8, fused via the live DecisionFusion.
            engine = BacktestEngine()  # default strategies + default (live) DecisionFusion
            report = await engine.run(bars, config)
            rows.append({
                "symbol": symbol, "timeframe": timeframe, "variant": "fusion:decision_fusion",
                "num_bars": report.num_bars, **_metrics_dict(report),
            })
    return rows


def compute_recommended_weights(grid_rows: list[dict[str, Any]]) -> dict[str, float]:
    """Derive per-strategy weights from real backtested solo performance
    at the primary timeframe, aggregated across every symbol.

    Method: for each strategy, average its Sharpe ratio and win rate
    across all 8 symbols (primary timeframe only, so the recommendation
    is grounded in one consistent, representative sample). Both metrics
    are min-max normalized to [0,1] across the 8 strategies, averaged
    into a composite score, then rescaled so the 8 weights have a mean
    of 1.0 (a weight of 1.5 means "50% more influence than the live
    engine's equal-confidence-only weighting"). Weights are clipped to
    [0.3, 2.0] so no strategy is ever fully silenced or allowed to
    dominate the vote outright — a deliberate, defensible risk choice
    given the study is over synthetic data, not a live-money guarantee.

    Args:
        grid_rows: Output of run_solo_and_fusion_grid().

    Returns:
        strategy_name -> recommended weight multiplier.
    """
    strategies = [s.name for s in default_strategies()]
    sharpe_by_strategy: dict[str, list[float]] = {s: [] for s in strategies}
    winrate_by_strategy: dict[str, list[float]] = {s: [] for s in strategies}

    for row in grid_rows:
        if row["timeframe"] != PRIMARY_TIMEFRAME or not row["variant"].startswith("strategy:"):
            continue
        name = row["variant"].split(":", 1)[1]
        if name in sharpe_by_strategy:
            sharpe_by_strategy[name].append(row["sharpe_ratio"])
            winrate_by_strategy[name].append(row["win_rate_pct"])

    avg_sharpe = {s: statistics.mean(v) if v else 0.0 for s, v in sharpe_by_strategy.items()}
    avg_winrate = {s: statistics.mean(v) if v else 0.0 for s, v in winrate_by_strategy.items()}

    def _minmax_normalize(values: dict[str, float]) -> dict[str, float]:
        lo, hi = min(values.values()), max(values.values())
        if hi - lo < 1e-9:
            return {k: 0.5 for k in values}
        return {k: (v - lo) / (hi - lo) for k, v in values.items()}

    norm_sharpe = _minmax_normalize(avg_sharpe)
    norm_winrate = _minmax_normalize(avg_winrate)

    composite = {s: 0.5 * norm_sharpe[s] + 0.5 * norm_winrate[s] for s in strategies}
    mean_composite = statistics.mean(composite.values()) or 1.0
    raw_weights = {s: composite[s] / mean_composite for s in strategies}
    clipped = {s: max(0.3, min(2.0, w)) for s, w in raw_weights.items()}

    # Re-center to mean 1.0 after clipping so the overall vote scale is unchanged.
    mean_clipped = statistics.mean(clipped.values()) or 1.0
    return {s: round(w / mean_clipped, 3) for s, w in clipped.items()}


async def run_fusion_method_comparison(weights: dict[str, float]) -> list[dict[str, Any]]:
    """At the primary timeframe, for every symbol, compare three fusion
    methods on the identical bar series: the live confidence-weighted
    DecisionFusion, unweighted MajorityVoteFusion, and WeightedFusion
    using the recommended per-strategy weights.
    """
    rows: list[dict[str, Any]] = []
    fusions = {
        "live_decision_fusion": None,  # None -> BacktestEngine's default (live DecisionFusion)
        "majority_vote": MajorityVoteFusion(),
        "optimized_weighted": WeightedFusion(weights),
    }
    for symbol in SYMBOLS:
        bars = _bars_for(symbol, PRIMARY_TIMEFRAME, FUSION_COMPARISON_BARS, tag="fusion-cmp")
        config = BacktestRunConfig(symbol=symbol)
        for label, fusion in fusions.items():
            engine = BacktestEngine(fusion=fusion) if fusion is not None else BacktestEngine()
            report = await engine.run(bars, config)
            rows.append({
                "symbol": symbol, "variant": label, "num_bars": report.num_bars, **_metrics_dict(report),
            })
    return rows


async def run_large_scale_flagship() -> list[dict[str, Any]]:
    """A few large (5,000-bar) end-to-end runs with the live DecisionFusion,
    the headline evidence for objective 1 ("run large-scale backtests").
    """
    rows: list[dict[str, Any]] = []
    for symbol in LARGE_SCALE_SYMBOLS:
        bars = _bars_for(symbol, PRIMARY_TIMEFRAME, LARGE_SCALE_BARS, tag="large-scale")
        config = BacktestRunConfig(symbol=symbol)
        engine = BacktestEngine()
        started = time.time()
        report = await engine.run(bars, config)
        elapsed = time.time() - started
        rows.append({
            "symbol": symbol, "num_bars": report.num_bars, "wall_clock_seconds": round(elapsed, 2),
            **_metrics_dict(report),
        })
    return rows


def verify_weighted_fusion_matches_live_at_neutral_weights(sample_signals) -> bool:  # noqa: ANN001
    """Sanity check: WeightedFusion with every weight=1.0 must produce
    the same decision as the live DecisionFusion, for the same inputs —
    confirms the research fusion is a true generalization, not a
    different algorithm being passed off as equivalent.
    """
    from intelligence.fusion import DecisionFusion

    live = DecisionFusion().combine(sample_signals)
    neutral = WeightedFusion({s.strategy_name: 1.0 for s in sample_signals}).combine(sample_signals)
    return live.direction == neutral.direction and abs(live.confidence - neutral.confidence) < 1e-9


async def run_full_study() -> dict[str, Any]:
    """Run the complete Sprint 6 study and return the full results bundle."""
    started_at = time.time()

    grid_rows = await run_solo_and_fusion_grid()
    weights = compute_recommended_weights(grid_rows)
    fusion_comparison_rows = await run_fusion_method_comparison(weights)
    large_scale_rows = await run_large_scale_flagship()

    return {
        "started_at": started_at,
        "completed_at": time.time(),
        "symbols": SYMBOLS,
        "timeframes": TIMEFRAMES,
        "grid_bars_per_run": GRID_BARS,
        "fusion_comparison_bars_per_run": FUSION_COMPARISON_BARS,
        "large_scale_bars_per_run": LARGE_SCALE_BARS,
        "grid_results": grid_rows,
        "recommended_weights": weights,
        "fusion_comparison_results": fusion_comparison_rows,
        "large_scale_results": large_scale_rows,
    }
