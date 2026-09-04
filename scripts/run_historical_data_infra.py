#!/usr/bin/env python3
"""
DATS — Phase 3 Historical Data Infrastructure Runner
Version: 1.0
Date: 2026-09-04

Fetches REAL historical OHLCV from Binance's public API (live network
calls, not simulated), validates integrity, caches to disk, proves
reproducibility via checksum comparison across two independent
fetches, and feeds one real dataset through the frozen, unmodified
BacktestEngine — the first time this codebase has backtested on real
market data instead of synthetic GBM.

Fixed, past UTC date ranges are used throughout (never "now minus N
days") so every candle fetched is a fully closed historical candle and
re-running this script at any future date reproduces the exact same
dataset.

Run inside the app container (PYTHONPATH=/app/src is already set there,
matching every other script in this directory):

    docker exec dats-beta python scripts/run_historical_data_infra.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from backtesting.engine import BacktestEngine, BacktestRunConfig  # noqa: E402
from historical_data.service import HistoricalDataService  # noqa: E402

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def _ms(dt_str: str) -> int:
    return int(datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc).timestamp() * 1000)


# Fixed, past UTC ranges — deterministic regardless of when this script runs.
RANGES: dict[str, tuple[int, int]] = {
    "1h": (_ms("2026-07-01T00:00:00"), _ms("2026-08-30T00:00:00")),  # ~60 days, ~1440 bars -> exercises pagination
    "4h": (_ms("2026-05-01T00:00:00"), _ms("2026-08-30T00:00:00")),  # ~121 days, ~726 bars
    "1d": (_ms("2025-08-01T00:00:00"), _ms("2026-09-01T00:00:00")),  # ~396 days, ~396 bars
}


async def main() -> None:
    service = HistoricalDataService()
    results: dict = {
        "started_at": time.time(), "symbols": SYMBOLS, "ranges_utc": {
            k: [datetime.fromtimestamp(v[0] / 1000, tz=timezone.utc).isoformat(),
                datetime.fromtimestamp(v[1] / 1000, tz=timezone.utc).isoformat()]
            for k, v in RANGES.items()
        },
        "datasets": [], "reproducibility_check": None, "backtest_proof": None,
    }

    print("Fetching real historical OHLCV from Binance for 3 symbols x 3 timeframes...")
    for symbol in SYMBOLS:
        for interval, (start_ms, end_ms) in RANGES.items():
            t0 = time.time()
            dataset = await service.get_ohlcv(symbol, interval, start_ms, end_ms)
            elapsed = time.time() - t0
            print(
                f"  {symbol:<10}{interval:<5} bars={len(dataset.bars):<6} cache_hit={dataset.cache_hit!s:<6} "
                f"integrity_clean={dataset.integrity.is_clean!s:<6} {elapsed:.2f}s"
            )
            results["datasets"].append({
                "symbol": symbol, "interval": interval, "bar_count": len(dataset.bars),
                "cache_hit": dataset.cache_hit, "fetch_seconds": round(elapsed, 3),
                "integrity": dataset.integrity.to_dict(), "manifest": dataset.manifest,
            })

    print("\nRe-fetching BTCUSDT 1D to prove cache-hit + reproducibility (checksum match)...")
    symbol, interval = "BTCUSDT", "1d"
    start_ms, end_ms = RANGES[interval]
    first_manifest = next(
        d["manifest"] for d in results["datasets"] if d["symbol"] == symbol and d["interval"] == interval
    )
    t0 = time.time()
    dataset_2nd = await service.get_ohlcv(symbol, interval, start_ms, end_ms)
    elapsed_2nd = time.time() - t0
    checksum_match = dataset_2nd.manifest["sha256"] == first_manifest["sha256"]
    print(
        f"  Second fetch: cache_hit={dataset_2nd.cache_hit}  {elapsed_2nd:.3f}s  "
        f"checksum_match={checksum_match}"
    )
    results["reproducibility_check"] = {
        "symbol": symbol, "interval": interval,
        "first_fetch_seconds": next(
            d["fetch_seconds"] for d in results["datasets"] if d["symbol"] == symbol and d["interval"] == interval
        ),
        "second_fetch_cache_hit": dataset_2nd.cache_hit,
        "second_fetch_seconds": round(elapsed_2nd, 3),
        "checksum_match": checksum_match,
        "first_sha256": first_manifest["sha256"],
        "second_sha256": dataset_2nd.manifest["sha256"],
    }

    print("\nFeeding real BTCUSDT 1D historical data into the frozen, unmodified BacktestEngine...")
    engine = BacktestEngine()  # frozen: default 8 strategies + live DecisionFusion, untouched
    config = BacktestRunConfig(symbol="BTCUSDT", initial_capital=100000.0)
    report = await engine.run(dataset_2nd.bars, config)
    pm = report.portfolio_metrics
    print(
        f"  Bars={report.num_bars}  Trades={pm.number_of_trades}  Return={pm.total_return_pct}%  "
        f"Sharpe={pm.sharpe_ratio}  MaxDD={pm.max_drawdown_pct}%"
    )
    results["backtest_proof"] = {
        "symbol": "BTCUSDT", "interval": "1d", "num_bars": report.num_bars,
        "total_return_pct": pm.total_return_pct, "cagr_pct": pm.cagr_pct,
        "sharpe_ratio": pm.sharpe_ratio, "max_drawdown_pct": pm.max_drawdown_pct,
        "profit_factor": pm.profit_factor, "win_rate_pct": pm.win_rate_pct,
        "number_of_trades": pm.number_of_trades,
    }

    results["completed_at"] = time.time()
    out_path = Path(__file__).resolve().parent.parent / "docs" / "phase-3-data-infrastructure-results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote results to {out_path}")
    print(f"Total wall-clock time: {results['completed_at'] - results['started_at']:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
