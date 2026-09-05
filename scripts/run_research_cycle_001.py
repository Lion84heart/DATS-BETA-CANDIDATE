#!/usr/bin/env python3
"""
DATS — Mission Research Cycle 1 Runner
Version: 1.0
Date: 2026-09-05

Runs Cycle 1's experiment grid (research.mission_study.run_cycle_1)
and writes the raw results to docs/research-cycle-001-results.json —
the source data behind docs/RESEARCH_CYCLE_001.md. Every number in
that report is transcribed from this file's output, not asserted
independently.

Before the grid runs, re-verifies that execution_intelligence's
managed backtest loop (recently given an additive `fusion=` parameter
for this mission) still reproduces the frozen BacktestEngine exactly
at baseline — a regression check on Phase 4's own module, not just a
one-time historical fact.

Run inside the app container (PYTHONPATH=/app/src is already set there,
matching every other script in this directory):

    docker exec dats-beta python scripts/run_research_cycle_001.py
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
from research.mission_study import run_cycle_1  # noqa: E402


async def _sanity_check() -> None:
    bars = generate_synthetic_ohlcv("AAPL", 300, seed=42)
    config = BacktestRunConfig(symbol="AAPL")
    ok = await verify_managed_loop_matches_baseline(bars, config)
    print(f"[sanity check] managed loop (with new fusion=/min_confidence= params) still matches frozen BacktestEngine at baseline: {ok}")
    if not ok:
        raise SystemExit("Managed loop regressed after the mission's additive changes — aborting.")


def _summarize(results: dict) -> None:
    print(f"\nExperiments: {results['num_experiments']}  Backtests: {results['num_backtests']}")
    print(f"Bars per symbol (train window {results['train_start']} -> {results['train_end']}): {results['bars_per_symbol']}")
    print(f"Holdout window (fetched, NOT used this cycle): {results['holdout_start']} -> {results['holdout_end']}")
    print(f"Holdout metadata: {results['holdout_metadata']}")

    passing = [s for s in results["config_summaries"] if s["all_symbols_pass_individually"]]
    print(f"\nConfigs passing ALL success criteria on EVERY symbol individually: {len(passing)}")
    for s in passing:
        print(f"  {s['strategy_subset']:<18}{s['fusion_method']:<20}conf={s['confidence_threshold']:<5}{s['trade_management']:<22}"
              f"avg_sharpe={s['avg_metrics']['sharpe_ratio']}  avg_pf={s['avg_metrics']['profit_factor']}  "
              f"avg_maxdd={s['avg_metrics']['max_drawdown_pct']}  avg_cagr={s['avg_metrics']['cagr_pct']}")

    print("\nTop 10 configs by average Sharpe (regardless of pass/fail):")
    for s in results["config_summaries"][:10]:
        print(f"  {s['strategy_subset']:<18}{s['fusion_method']:<20}conf={s['confidence_threshold']:<5}{s['trade_management']:<22}"
              f"avg_sharpe={s['avg_metrics']['sharpe_ratio']}  avg_pf={s['avg_metrics']['profit_factor']}  "
              f"avg_maxdd={s['avg_metrics']['max_drawdown_pct']}  avg_cagr={s['avg_metrics']['cagr_pct']}  "
              f"all_pass={s['all_symbols_pass_individually']}")

    elapsed = results["completed_at"] - results["started_at"]
    print(f"\nTotal study wall-clock time: {elapsed:.1f}s")


async def main() -> None:
    await _sanity_check()
    print("Running Mission Research Cycle 1 (this will take a while — hundreds of backtests)...")
    started = time.time()
    results = await run_cycle_1()
    print(f"Cycle complete in {time.time() - started:.1f}s wall-clock.")

    out_path = Path(__file__).resolve().parent.parent / "docs" / "research-cycle-001-results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"Wrote raw results to {out_path}")

    _summarize(results)


if __name__ == "__main__":
    asyncio.run(main())
