#!/usr/bin/env python3
"""
DATS — Sprint 6 Quantitative Research Runner
Version: 1.0
Date: 2026-09-04

Runs the full Sprint 6 study (research.study.run_full_study) and writes
the raw results to docs/sprint-6-research-results.json — the source
data behind docs/SPRINT-6-QUANT-REPORT.md. Every number in that report
is transcribed from this file's output, not asserted independently.

Run inside the app container (PYTHONPATH=/app/src is already set there,
matching every other script in this directory):

    docker exec dats-beta python scripts/run_quant_research.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from research.study import run_full_study, verify_weighted_fusion_matches_live_at_neutral_weights  # noqa: E402
from trading.schemas import SignalDirection, StrategySignal  # noqa: E402


def _sanity_check() -> None:
    """Fail fast if the research WeightedFusion isn't a true generalization
    of the live DecisionFusion at neutral (1.0) weights."""
    sample = [
        StrategySignal(symbol="TEST", direction=SignalDirection.BUY, confidence=0.7, strategy_name="a"),
        StrategySignal(symbol="TEST", direction=SignalDirection.BUY, confidence=0.4, strategy_name="b"),
        StrategySignal(symbol="TEST", direction=SignalDirection.SELL, confidence=0.9, strategy_name="c"),
        StrategySignal(symbol="TEST", direction=SignalDirection.HOLD, confidence=0.2, strategy_name="d"),
    ]
    ok = verify_weighted_fusion_matches_live_at_neutral_weights(sample)
    print(f"[sanity check] WeightedFusion(weights=1.0) matches live DecisionFusion: {ok}")
    if not ok:
        raise SystemExit("WeightedFusion at neutral weights diverged from live DecisionFusion — aborting.")


def _summarize(results: dict) -> None:
    grid = results["grid_results"]
    print(f"\nGrid runs: {len(grid)}")
    print(f"Fusion comparison runs: {len(results['fusion_comparison_results'])}")
    print(f"Large-scale runs: {len(results['large_scale_results'])}")
    print(f"\nRecommended weights: {json.dumps(results['recommended_weights'], indent=2)}")

    elapsed = results["completed_at"] - results["started_at"]
    print(f"\nTotal study wall-clock time: {elapsed:.1f}s")

    for row in results["large_scale_results"]:
        print(
            f"  large-scale {row['symbol']}: {row['num_bars']} bars in {row['wall_clock_seconds']}s, "
            f"total_return={row['total_return_pct']}%, sharpe={row['sharpe_ratio']}, trades={row['number_of_trades']}"
        )


async def main() -> None:
    _sanity_check()
    print("Running Sprint 6 quantitative research study (this will take a few minutes)...")
    started = time.time()
    results = await run_full_study()
    print(f"Study complete in {time.time() - started:.1f}s wall-clock.")

    out_path = Path(__file__).resolve().parent.parent / "docs" / "sprint-6-research-results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"Wrote raw results to {out_path}")

    _summarize(results)


if __name__ == "__main__":
    asyncio.run(main())
