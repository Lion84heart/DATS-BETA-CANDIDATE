#!/usr/bin/env python3
"""
DATS — Phase 4 Trade Management Intelligence Runner
Version: 1.0
Date: 2026-09-04

Runs the full Phase 4 study (execution_intelligence.phase4_study.run_full_phase4_study)
and writes the raw results to docs/phase-4-trade-management-results.json
— the source data behind docs/PHASE-4-TRADE-MANAGEMENT-REPORT.md. Every
number in that report is transcribed from this file's output, not
asserted independently.

Run inside the app container (PYTHONPATH=/app/src is already set there,
matching every other script in this directory):

    docker exec dats-beta python scripts/run_phase4_trade_management.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from backtesting.data import generate_synthetic_ohlcv  # noqa: E402
from backtesting.engine import BacktestRunConfig  # noqa: E402
from execution_intelligence.managed_backtest import verify_managed_loop_matches_baseline  # noqa: E402
from execution_intelligence.phase4_study import run_full_phase4_study  # noqa: E402


async def _sanity_check() -> None:
    """Fail fast if the managed backtest loop isn't a true
    reimplementation of the frozen BacktestEngine's semantics at
    all-toggles-off (baseline)."""
    bars = generate_synthetic_ohlcv("AAPL", 300, seed=42)
    config = BacktestRunConfig(symbol="AAPL")
    ok = await verify_managed_loop_matches_baseline(bars, config)
    print(f"[sanity check] managed loop matches frozen BacktestEngine at baseline (all toggles off): {ok}")
    if not ok:
        raise SystemExit("Managed loop diverged from the frozen BacktestEngine at baseline — aborting.")


def _summarize(results: dict) -> None:
    print(f"\nGrid runs: {len(results['grid_results'])}")
    print(f"\nPer-variant summary (avg across all price series):")
    for variant, agg in results["variant_summary"].items():
        line = (
            f"  {variant:<22} sharpe={agg['avg_sharpe_ratio']!s:>8}  maxdd={agg['avg_max_drawdown_pct']!s:>8}  "
            f"cagr={agg['avg_cagr_pct']!s:>8}  pf={agg['avg_profit_factor']!s:>8}  trades={agg['avg_number_of_trades']!s:>6}"
        )
        if "sharpe_win_rate_vs_baseline_pct" in agg:
            line += f"  win_vs_baseline={agg['sharpe_win_rate_vs_baseline_pct']}%  delta_sharpe={agg['delta_avg_sharpe_vs_baseline']}"
        print(line)

    elapsed = results["completed_at"] - results["started_at"]
    print(f"\nTotal study wall-clock time: {elapsed:.1f}s")


async def main() -> None:
    await _sanity_check()
    print("Running Phase 4 trade management study (this will take several minutes)...")
    started = time.time()
    results = await run_full_phase4_study()
    print(f"Study complete in {time.time() - started:.1f}s wall-clock.")

    out_path = Path(__file__).resolve().parent.parent / "docs" / "phase-4-trade-management-results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"Wrote raw results to {out_path}")

    _summarize(results)


if __name__ == "__main__":
    asyncio.run(main())
