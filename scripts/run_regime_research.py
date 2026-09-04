#!/usr/bin/env python3
"""
DATS — Phase 2 Market Regime Engine Research Runner
Version: 1.0
Date: 2026-09-04

Runs the full Phase 2 study (research.regime_study.run_full_regime_study)
and writes the raw results to docs/phase-2-regime-results.json — the
source data behind docs/PHASE-2-REGIME-REPORT.md. Every number in that
report is transcribed from this file's output, not asserted independently.

Run inside the app container (PYTHONPATH=/app/src is already set there,
matching every other script in this directory):

    docker exec dats-beta python scripts/run_regime_research.py
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
from research.regime_backtest import verify_regime_loop_matches_static_at_neutral_weights  # noqa: E402
from research.regime_study import run_full_regime_study  # noqa: E402


async def _sanity_check() -> None:
    """Fail fast if the regime-aware loop isn't a true reimplementation
    of the frozen BacktestEngine's semantics at neutral (1.0) weights."""
    bars = generate_synthetic_ohlcv("AAPL", 300, seed=42)
    config = BacktestRunConfig(symbol="AAPL")
    ok = await verify_regime_loop_matches_static_at_neutral_weights(bars, config)
    print(f"[sanity check] regime-aware loop matches static BacktestEngine at neutral (1.0) weights: {ok}")
    if not ok:
        raise SystemExit("Regime-aware loop diverged from the frozen BacktestEngine at neutral weights — aborting.")


def _summarize(results: dict) -> None:
    grid = results["comparison_grid_results"]
    print(f"\nComparison grid runs: {len(grid)}")
    print(f"\nRegime routing weights:\n{json.dumps(results['regime_routing_weights'], indent=2)}")

    elapsed = results["completed_at"] - results["started_at"]
    print(f"\nTotal study wall-clock time: {elapsed:.1f}s")


async def main() -> None:
    await _sanity_check()
    print("Running Phase 2 Market Regime Engine research study (this will take a few minutes)...")
    started = time.time()
    results = await run_full_regime_study()
    print(f"Study complete in {time.time() - started:.1f}s wall-clock.")

    out_path = Path(__file__).resolve().parent.parent / "docs" / "phase-2-regime-results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"Wrote raw results to {out_path}")

    _summarize(results)


if __name__ == "__main__":
    asyncio.run(main())
