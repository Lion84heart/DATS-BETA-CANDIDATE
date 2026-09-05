"""Mission Research Cycle 1 orchestration.

Fetches real, long-horizon Binance daily OHLCV for BTCUSDT/ETHUSDT/
SOLUSDT — a multi-year window spanning real bull, bear, and sideways
regimes, not a cherry-picked slice — splits it into a **training**
window (used for this cycle's hypothesis-generating grid search) and a
completely separate, later **holdout** window that is fetched and
recorded here but deliberately NOT touched by any experiment in this
cycle — it exists so a later cycle can validate whatever candidate(s)
survive training-window screening without ever having been used to
pick or tune them.

Every experiment reuses existing, already-tested machinery: the frozen
Strategy Engine (via subset selection, not modification), the real
`DecisionFusion` or Sprint 6's already-verified `MajorityVoteFusion`,
and Phase 4's already-built `execution_intelligence` trade-management
stack. Nothing here is a new indicator, strategy, or fusion algorithm.
"""

from __future__ import annotations

import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from historical_data.service import HistoricalDataService
from research.mission_backtest import run_experiment
from research.mission_config import build_experiment_grid, meets_success_criteria

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# Real, multi-year window spanning the 2021 bull run, the 2022 bear market
# (Terra/LUNA, FTX), and the 2023-2024 recovery — training only.
TRAIN_START = "2021-01-01T00:00:00"
TRAIN_END = "2024-07-01T00:00:00"

# Held out, later, non-overlapping window — fetched and recorded for a
# future validation cycle, never used to pick or tune anything here.
HOLDOUT_START = "2024-07-01T00:00:00"
HOLDOUT_END = "2026-09-01T00:00:00"


def _ms(dt_str: str) -> int:
    return int(datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc).timestamp() * 1000)


async def fetch_train_bars() -> dict[str, list]:
    service = HistoricalDataService()
    bars_by_symbol: dict[str, list] = {}
    for symbol in SYMBOLS:
        dataset = await service.get_ohlcv(symbol, "1d", _ms(TRAIN_START), _ms(TRAIN_END))
        bars_by_symbol[symbol] = dataset.bars
    return bars_by_symbol


async def fetch_and_record_holdout_metadata() -> dict[str, Any]:
    """Fetches the holdout window (so it's cached, checksummed, and its
    existence/row-counts are on record) WITHOUT running any experiment
    against it — this cycle only reports what it contains, never what
    any candidate does on it."""
    service = HistoricalDataService()
    meta: dict[str, Any] = {}
    for symbol in SYMBOLS:
        dataset = await service.get_ohlcv(symbol, "1d", _ms(HOLDOUT_START), _ms(HOLDOUT_END))
        meta[symbol] = {"bar_count": len(dataset.bars), "integrity_clean": dataset.integrity.is_clean}
    return meta


def _avg(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(statistics.mean(vals), 4) if vals else None


def summarize_and_flag_candidates(grid_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group by experiment config across the 3 symbols, compute averaged
    metrics, and flag whether the config clears the mission's success
    criteria on the AVERAGE and — the stricter, more meaningful bar —
    on EVERY individual symbol. The mission requires robustness across
    multiple symbols; passing on average while failing on one symbol
    does not count as a real candidate.
    """
    grouped: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in grid_results:
        key = (r["strategy_subset"], r["fusion_method"], r["confidence_threshold"], r["trade_management"])
        grouped[key].append(r)

    summaries: list[dict[str, Any]] = []
    for key, rows in grouped.items():
        avg_metrics = {
            "profit_factor": _avg(rows, "profit_factor"),
            "sharpe_ratio": _avg(rows, "sharpe_ratio"),
            "max_drawdown_pct": _avg(rows, "max_drawdown_pct"),
            "cagr_pct": _avg(rows, "cagr_pct"),
            "total_return_pct": _avg(rows, "total_return_pct"),
            "win_rate_pct": _avg(rows, "win_rate_pct"),
            "number_of_trades": _avg(rows, "number_of_trades"),
        }
        per_symbol_pass = {r["symbol"]: meets_success_criteria(r) for r in rows}
        summaries.append({
            "strategy_subset": key[0], "fusion_method": key[1],
            "confidence_threshold": key[2], "trade_management": key[3],
            "avg_metrics": avg_metrics,
            "per_symbol_metrics": {
                r["symbol"]: {
                    "profit_factor": r.get("profit_factor"), "sharpe_ratio": r.get("sharpe_ratio"),
                    "max_drawdown_pct": r.get("max_drawdown_pct"), "cagr_pct": r.get("cagr_pct"),
                    "number_of_trades": r.get("number_of_trades"),
                }
                for r in rows
            },
            "per_symbol_pass": per_symbol_pass,
            "avg_passes_criteria": meets_success_criteria(avg_metrics),
            "all_symbols_pass_individually": all(per_symbol_pass.values()),
        })

    summaries.sort(key=lambda s: (s["avg_metrics"]["sharpe_ratio"] or -999), reverse=True)
    return summaries


async def run_cycle_1() -> dict[str, Any]:
    started_at = time.time()

    bars_by_symbol = await fetch_train_bars()
    holdout_meta = await fetch_and_record_holdout_metadata()

    grid = build_experiment_grid()
    rows: list[dict[str, Any]] = []
    for experiment in grid:
        for symbol, bars in bars_by_symbol.items():
            metrics, extra = await run_experiment(bars, symbol, experiment)
            rows.append({
                "symbol": symbol,
                "strategy_subset": experiment.strategy_subset,
                "fusion_method": experiment.fusion_method,
                "confidence_threshold": experiment.confidence_threshold,
                "trade_management": experiment.trade_management,
                **metrics,
                "extra": extra,
            })

    summaries = summarize_and_flag_candidates(rows)

    return {
        "started_at": started_at, "completed_at": time.time(),
        "symbols": SYMBOLS,
        "train_start": TRAIN_START, "train_end": TRAIN_END,
        "holdout_start": HOLDOUT_START, "holdout_end": HOLDOUT_END,
        "holdout_metadata": holdout_meta,
        "num_experiments": len(grid), "num_backtests": len(rows),
        "bars_per_symbol": {s: len(b) for s, b in bars_by_symbol.items()},
        "grid_results": rows,
        "config_summaries": summaries,
    }
