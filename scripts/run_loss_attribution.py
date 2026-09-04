#!/usr/bin/env python3
"""
DATS — Sprint 7 Loss Attribution & Edge Analysis Runner
Version: 1.0
Date: 2026-09-04

Runs the full Sprint 7 study (research.loss_attribution_study.run_full_loss_attribution_study)
and writes the raw results to docs/sprint-7-loss-attribution-results.json
— the source data behind docs/LOSS_ATTRIBUTION_REPORT.md. Every number
in that report is transcribed from this file's output, not asserted
independently.

Run inside the app container (PYTHONPATH=/app/src is already set there,
matching every other script in this directory):

    docker exec dats-beta python scripts/run_loss_attribution.py
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
from research.loss_attribution_study import run_full_loss_attribution_study  # noqa: E402
from research.trade_forensics import verify_forensic_loop_matches_static  # noqa: E402


async def _sanity_check() -> None:
    """Fail fast if the instrumented forensic loop isn't a true
    reimplementation of the frozen BacktestEngine's semantics."""
    bars = generate_synthetic_ohlcv("AAPL", 300, seed=42)
    config = BacktestRunConfig(symbol="AAPL")
    ok = await verify_forensic_loop_matches_static(bars, config)
    print(f"[sanity check] forensic loop matches static BacktestEngine exactly: {ok}")
    if not ok:
        raise SystemExit("Forensic loop diverged from the frozen BacktestEngine — aborting.")


def _summarize(results: dict) -> None:
    combined = results["aggregate_combined"]
    real = results["aggregate_real_only"]
    synthetic = results["aggregate_synthetic_only"]

    print(f"\nCombined: {combined['total_trades']} trades, {combined['losing_trades']} losers "
          f"({combined['loss_rate_pct']}% loss rate)")
    print(f"Real (Binance) only: {real['total_trades']} trades, {real['losing_trades']} losers "
          f"({real['loss_rate_pct']}% loss rate)")
    print(f"Synthetic only: {synthetic['total_trades']} trades, {synthetic['losing_trades']} losers "
          f"({synthetic['loss_rate_pct']}% loss rate)")

    print("\nRepeated failure patterns (combined):")
    for tag, info in combined["repeated_failure_patterns"].items():
        print(f"  {tag:<20} {info['count']:>4} ({info['pct_of_losers']}% of losers)")

    print(f"\nOvertrading-flagged runs: {len(combined['overtrading_flagged_runs'])}")
    for r in combined["overtrading_flagged_runs"]:
        print(f"  {r['symbol']:<10}{r['timeframe']:<5}{r['source']:<10} "
              f"trades/100bars={r['trades_per_100_bars']}  avg_hold={r['avg_holding_time_bars']}")

    elapsed = results["completed_at"] - results["started_at"]
    print(f"\nTotal study wall-clock time: {elapsed:.1f}s")


async def main() -> None:
    await _sanity_check()
    print("Running Sprint 7 loss attribution study (this will take a few minutes)...")
    started = time.time()
    results = await run_full_loss_attribution_study()
    print(f"Study complete in {time.time() - started:.1f}s wall-clock.")

    out_path = Path(__file__).resolve().parent.parent / "docs" / "sprint-7-loss-attribution-results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"Wrote raw results to {out_path}")

    _summarize(results)


if __name__ == "__main__":
    asyncio.run(main())
