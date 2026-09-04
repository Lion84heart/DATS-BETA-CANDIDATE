"""Phase 4 — Trade Management Intelligence orchestration.

Backtests every module independently (Objective 9) plus the fully
combined "risk-adjusted execution" system, against the frozen baseline
(Objective 10), across real Binance data (Phase 3's exact fixed date
ranges — same cached, checksummed data) and a supplementary synthetic
grid (Sprint 6/Phase 2/Sprint 7's symbol universe, primary timeframe
only — the trade-management question this phase asks doesn't need the
full 3-timeframe grid to get a robust read, and keeping the run
tractable matters more here given 8 variants per price series).

Eight variants per (symbol, timeframe):
  - baseline               — every toggle off; must equal the frozen
                              BacktestEngine exactly (verified, not assumed).
  - entry_filter_only       — Objective 1 alone.
  - atr_stop_only           — Objective 3 alone.
  - trailing_stop_only      — Objective 4 alone.
  - breakeven_only          — Objective 5 alone.
  - position_sizing_only    — Objective 6 alone.
  - dynamic_exit_engine     — Objectives 3+4+5 combined (module 2).
  - full_risk_adjusted      — everything combined (Objective 8).

Nothing here modifies trading/strategies/*, intelligence/fusion.py,
intelligence/engine.py, trading/execution/*, or backtesting/engine.py.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from backtesting.engine import BacktestRunConfig
from execution_intelligence.managed_backtest import ManagedBacktestConfig, run_managed_backtest
from historical_data.service import HistoricalDataService
from research.study import SYMBOLS, PRIMARY_TIMEFRAME, _bars_for

REAL_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def _ms(dt_str: str) -> int:
    return int(datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc).timestamp() * 1000)


# Identical to Phase 3's / Sprint 7's fixed ranges: same cached data, same reproducibility.
REAL_RANGES: dict[str, tuple[int, int]] = {
    "1h": (_ms("2026-07-01T00:00:00"), _ms("2026-08-30T00:00:00")),
    "4h": (_ms("2026-05-01T00:00:00"), _ms("2026-08-30T00:00:00")),
    "1d": (_ms("2025-08-01T00:00:00"), _ms("2026-09-01T00:00:00")),
}

SYNTHETIC_BARS = 1000
SYNTHETIC_TAG = "phase4"

VARIANTS: dict[str, ManagedBacktestConfig] = {
    "baseline": ManagedBacktestConfig(),
    "entry_filter_only": ManagedBacktestConfig(use_entry_filter=True),
    "atr_stop_only": ManagedBacktestConfig(use_atr_stop=True),
    "trailing_stop_only": ManagedBacktestConfig(use_trailing_stop=True),
    "breakeven_only": ManagedBacktestConfig(use_breakeven=True),
    "position_sizing_only": ManagedBacktestConfig(use_position_sizing=True),
    "dynamic_exit_engine": ManagedBacktestConfig(use_atr_stop=True, use_trailing_stop=True, use_breakeven=True),
    "full_risk_adjusted": ManagedBacktestConfig(
        use_entry_filter=True, use_atr_stop=True, use_trailing_stop=True,
        use_breakeven=True, use_position_sizing=True,
    ),
}


def _metrics_dict(report) -> dict[str, Any]:  # noqa: ANN001 - BacktestReport, avoid import cycle
    return asdict(report.portfolio_metrics)


async def _run_all_variants(symbol: str, timeframe: str, source: str, bars) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    config = BacktestRunConfig(symbol=symbol)
    for variant_name, managed_config in VARIANTS.items():
        report, extra = await run_managed_backtest(bars, config, managed_config)
        rows.append({
            "symbol": symbol, "timeframe": timeframe, "source": source, "variant": variant_name,
            "num_bars": report.num_bars, **_metrics_dict(report), **extra,
        })
    return rows


async def run_comparison_grid() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    service = HistoricalDataService()
    for symbol in REAL_SYMBOLS:
        for interval, (start_ms, end_ms) in REAL_RANGES.items():
            dataset = await service.get_ohlcv(symbol, interval, start_ms, end_ms)
            rows.extend(await _run_all_variants(symbol, interval, "binance", dataset.bars))

    for symbol in SYMBOLS:
        bars = _bars_for(symbol, PRIMARY_TIMEFRAME, SYNTHETIC_BARS, tag=SYNTHETIC_TAG)
        rows.extend(await _run_all_variants(symbol, PRIMARY_TIMEFRAME, "synthetic", bars))

    return rows


def _avg(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(statistics.mean(vals), 4) if vals else None


def summarize_variants(grid_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-variant aggregate metrics (across all price series) plus a
    paired win-count against baseline for each non-baseline variant."""
    by_variant: dict[str, list[dict[str, Any]]] = {}
    for row in grid_rows:
        by_variant.setdefault(row["variant"], []).append(row)

    baseline_by_key = {(r["symbol"], r["timeframe"], r["source"]): r for r in by_variant["baseline"]}
    baseline_avg_sharpe = _avg(by_variant["baseline"], "sharpe_ratio")

    summary: dict[str, Any] = {}
    for variant_name, rows in by_variant.items():
        agg = {
            "avg_sharpe_ratio": _avg(rows, "sharpe_ratio"),
            "avg_max_drawdown_pct": _avg(rows, "max_drawdown_pct"),
            "avg_cagr_pct": _avg(rows, "cagr_pct"),
            "avg_profit_factor": _avg(rows, "profit_factor"),
            "avg_total_return_pct": _avg(rows, "total_return_pct"),
            "avg_win_rate_pct": _avg(rows, "win_rate_pct"),
            "avg_number_of_trades": _avg(rows, "number_of_trades"),
        }
        if variant_name != "baseline":
            wins = 0
            comparable = 0
            for r in rows:
                key = (r["symbol"], r["timeframe"], r["source"])
                base = baseline_by_key.get(key)
                if base is None:
                    continue
                comparable += 1
                if r["sharpe_ratio"] > base["sharpe_ratio"]:
                    wins += 1
            agg["sharpe_win_count_vs_baseline"] = wins
            agg["sharpe_comparable_runs"] = comparable
            agg["sharpe_win_rate_vs_baseline_pct"] = round(wins / comparable * 100, 2) if comparable else None
            if baseline_avg_sharpe is not None and agg["avg_sharpe_ratio"] is not None:
                agg["delta_avg_sharpe_vs_baseline"] = round(agg["avg_sharpe_ratio"] - baseline_avg_sharpe, 4)
            else:
                agg["delta_avg_sharpe_vs_baseline"] = None
        summary[variant_name] = agg

    return summary


async def run_full_phase4_study() -> dict[str, Any]:
    started_at = time.time()
    grid_rows = await run_comparison_grid()
    summary = summarize_variants(grid_rows)
    return {
        "started_at": started_at, "completed_at": time.time(),
        "real_symbols": REAL_SYMBOLS, "synthetic_symbols": SYMBOLS,
        "primary_timeframe": PRIMARY_TIMEFRAME, "synthetic_bars": SYNTHETIC_BARS,
        "variants": list(VARIANTS.keys()),
        "grid_results": grid_rows,
        "variant_summary": summary,
    }
