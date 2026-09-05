"""Mission research configuration: the axes a research cycle searches
over, plus the success criteria a candidate must clear.

Deliberately reuses only what already exists — the 8 frozen strategies
(``backtesting.engine.default_strategies``), the real frozen
``DecisionFusion``, Sprint 6's already-verified ``MajorityVoteFusion``
research variant, and Phase 4's already-built (not yet deployed)
``execution_intelligence`` trade-management modules. No new indicator,
no new strategy, no new fusion algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass

from execution_intelligence.managed_backtest import ManagedBacktestConfig
from research.fusion_variants import MajorityVoteFusion

# ---------------------------------------------------------------------------
# Success criteria (from the mission brief) — a candidate must clear ALL of
# these, not just one, to be considered for progression toward paper trading.
# ---------------------------------------------------------------------------

MIN_PROFIT_FACTOR = 1.50
MIN_SHARPE = 1.20
MAX_DRAWDOWN_PCT = 15.0
MIN_CAGR_PCT = 0.0  # "positive CAGR"

# ---------------------------------------------------------------------------
# Strategy subsets. "all_8" is the current live default. The other three are
# hypotheses grounded in prior research, not guesses:
#   - drop_weakest_2: Sprint 6 found EMA Cross and Trend Detection had the
#     lowest solo Sharpe (0.178, 0.049) of all 8 strategies.
#   - top_4_sharpe: Sprint 6's top 4 solo performers by Sharpe (Volume
#     Profile, Support/Resistance, VWAP, Bollinger Bands).
#   - protective_pair: Sprint 7 found ATR and Trend Detection were the two
#     strategies whose agreement correlated with WINNING trades (negative
#     loss-delta) — paired here with the two steadiest solo performers
#     (Support/Resistance, Bollinger Bands) as a hypothesis worth testing on
#     its own terms, not because Sprint 7's finding was itself confirmatory.
# ---------------------------------------------------------------------------

STRATEGY_SUBSETS: dict[str, set[str] | None] = {
    "all_8": None,  # None -> use every strategy (the current default)
    "drop_weakest_2": {
        "rsi", "vwap", "atr", "bollinger_bands", "support_resistance", "volume_profile",
    },
    "top_4_sharpe": {"volume_profile", "support_resistance", "vwap", "bollinger_bands"},
    "protective_pair": {"atr", "trend_detection", "support_resistance", "bollinger_bands"},
}

# ---------------------------------------------------------------------------
# Fusion methods. WeightedFusion with custom weights is deliberately held
# back for a later cycle (Sprint 6 already found weighted-vs-majority was a
# near-tie on synthetic data — re-testing it on real data is a distinct,
# separate hypothesis worth its own cycle rather than combining variables).
# ---------------------------------------------------------------------------

FUSION_METHODS: dict[str, object | None] = {
    "live_decision_fusion": None,  # None -> the real, unmodified DecisionFusion()
    "majority_vote": MajorityVoteFusion(),
}

# ---------------------------------------------------------------------------
# Confidence entry gate — a raw fused-confidence cutoff, independent of
# Phase 4's Trade Quality Score filter.
# ---------------------------------------------------------------------------

CONFIDENCE_THRESHOLDS: list[float] = [0.0, 0.5, 0.6]

# ---------------------------------------------------------------------------
# Trade-management presets, reusing Phase 4's execution_intelligence
# module toggles verbatim. "full_risk_adjusted" and "position_sizing_only"
# were Phase 4's two most promising (though not yet statistically proven on
# Sharpe) configurations; "none" is the current live-equivalent baseline.
# ---------------------------------------------------------------------------


def trade_management_presets() -> dict[str, ManagedBacktestConfig]:
    return {
        "none": ManagedBacktestConfig(),
        "position_sizing_only": ManagedBacktestConfig(use_position_sizing=True),
        "full_risk_adjusted": ManagedBacktestConfig(
            use_entry_filter=True, use_atr_stop=True, use_trailing_stop=True,
            use_breakeven=True, use_position_sizing=True,
        ),
    }


@dataclass(frozen=True)
class ExperimentConfig:
    """One point in the Cycle 1 grid."""

    strategy_subset: str
    fusion_method: str
    confidence_threshold: float
    trade_management: str


def build_experiment_grid() -> list[ExperimentConfig]:
    grid: list[ExperimentConfig] = []
    for subset_name in STRATEGY_SUBSETS:
        for fusion_name in FUSION_METHODS:
            for conf in CONFIDENCE_THRESHOLDS:
                for tm_name in trade_management_presets():
                    grid.append(ExperimentConfig(subset_name, fusion_name, conf, tm_name))
    return grid


def meets_success_criteria(metrics: dict[str, float | None]) -> bool:
    pf = metrics.get("profit_factor")
    sharpe = metrics.get("sharpe_ratio")
    maxdd = metrics.get("max_drawdown_pct")
    cagr = metrics.get("cagr_pct")
    if pf is None or sharpe is None or maxdd is None or cagr is None:
        return False
    return pf > MIN_PROFIT_FACTOR and sharpe > MIN_SHARPE and maxdd < MAX_DRAWDOWN_PCT and cagr > MIN_CAGR_PCT
