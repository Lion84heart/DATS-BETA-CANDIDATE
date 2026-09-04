"""Sprint 7 — Loss Attribution & Edge Analysis orchestration.

Runs the instrumented forensic backtest loop (``research.trade_forensics``,
which makes IDENTICAL decisions to the frozen ``BacktestEngine``/
``DecisionFusion`` — verified, not assumed) over real Binance
historical data (the exact fixed date ranges Phase 3 already fetched
and cached) plus a supplementary synthetic grid (Sprint 6/Phase 2's
existing symbol/timeframe universe), computes per-trade forensics
(``research.loss_classification``), and aggregates loss-attribution
statistics across the combined trade population.

Nothing here modifies ``trading/strategies/*``, ``intelligence/fusion.py``,
``intelligence/engine.py``, ``trading/execution/*``, or
``backtesting/engine.py``. No fixes are implemented — this module only
explains what already happened.
"""

from __future__ import annotations

import statistics
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from backtesting.engine import BacktestRunConfig, default_strategies
from historical_data.service import HistoricalDataService
from research.loss_classification import compute_trade_forensics
from research.study import SYMBOLS, TIMEFRAMES, _bars_for
from research.trade_forensics import run_forensic_backtest

REAL_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def _ms(dt_str: str) -> int:
    return int(datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc).timestamp() * 1000)


# Identical to Phase 3's fixed ranges: same cached data, same reproducibility.
REAL_RANGES: dict[str, tuple[int, int]] = {
    "1h": (_ms("2026-07-01T00:00:00"), _ms("2026-08-30T00:00:00")),
    "4h": (_ms("2026-05-01T00:00:00"), _ms("2026-08-30T00:00:00")),
    "1d": (_ms("2025-08-01T00:00:00"), _ms("2026-09-01T00:00:00")),
}

SYNTHETIC_BARS = 1000
SYNTHETIC_TAG = "loss-attribution"

_STRATEGY_NAMES = [s.name for s in default_strategies()]


def _run_summary(symbol: str, timeframe: str, source: str, forensic_run, trades) -> dict[str, Any]:
    pm = forensic_run.report.portfolio_metrics
    num_bars = forensic_run.report.num_bars
    return {
        "symbol": symbol, "timeframe": timeframe, "source": source,
        "num_bars": num_bars, "number_of_trades": pm.number_of_trades,
        "total_return_pct": pm.total_return_pct, "sharpe_ratio": pm.sharpe_ratio,
        "avg_holding_time_bars": pm.average_hold_time_bars,
        "trades_per_100_bars": round(pm.number_of_trades / num_bars * 100, 4) if num_bars else 0.0,
        "overtrading_flagged": False,
        "trades": [t.to_dict() for t in trades],
    }


async def _run_real_data() -> list[dict[str, Any]]:
    service = HistoricalDataService()
    run_summaries: list[dict[str, Any]] = []
    for symbol in REAL_SYMBOLS:
        for interval, (start_ms, end_ms) in REAL_RANGES.items():
            dataset = await service.get_ohlcv(symbol, interval, start_ms, end_ms)
            config = BacktestRunConfig(symbol=symbol)
            forensic_run = await run_forensic_backtest(dataset.bars, config)
            trades = compute_trade_forensics(
                symbol=symbol, timeframe=interval, source="binance",
                bars=forensic_run.bars, trades=forensic_run.report.trades,
                per_bar_strategy_directions=forensic_run.per_bar_strategy_directions,
                per_bar_fused_direction=forensic_run.per_bar_fused_direction,
            )
            run_summaries.append(_run_summary(symbol, interval, "binance", forensic_run, trades))
    return run_summaries


async def _run_synthetic_data() -> list[dict[str, Any]]:
    run_summaries: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            bars = _bars_for(symbol, timeframe, SYNTHETIC_BARS, tag=SYNTHETIC_TAG)
            config = BacktestRunConfig(symbol=symbol)
            forensic_run = await run_forensic_backtest(bars, config)
            trades = compute_trade_forensics(
                symbol=symbol, timeframe=timeframe, source="synthetic",
                bars=forensic_run.bars, trades=forensic_run.report.trades,
                per_bar_strategy_directions=forensic_run.per_bar_strategy_directions,
                per_bar_fused_direction=forensic_run.per_bar_fused_direction,
            )
            run_summaries.append(_run_summary(symbol, timeframe, "synthetic", forensic_run, trades))
    return run_summaries


def _flag_overtrading(run_summaries: list[dict[str, Any]]) -> None:
    """Flags runs whose trade frequency is notably higher than the
    cross-run median for their own data source (real vs. synthetic
    trade naturally at different frequencies, so medians are computed
    separately) AND whose average holding time is short — then tags
    every losing trade in a flagged run with 'overtrading'. Mutates
    ``run_summaries`` in place.
    """
    for source in {r["source"] for r in run_summaries}:
        group = [r for r in run_summaries if r["source"] == source]
        freqs = [r["trades_per_100_bars"] for r in group if r["number_of_trades"] > 0]
        if not freqs:
            continue
        median_freq = statistics.median(freqs)
        hold_times = [r["avg_holding_time_bars"] for r in group if r["number_of_trades"] > 0]
        median_hold = statistics.median(hold_times) if hold_times else 0.0

        for run in group:
            is_overtrading = (
                run["number_of_trades"] > 0 and median_freq > 0
                and run["trades_per_100_bars"] > 1.5 * median_freq
                and run["avg_holding_time_bars"] < median_hold
            )
            run["overtrading_flagged"] = is_overtrading
            if is_overtrading:
                for trade in run["trades"]:
                    if trade["is_loss"] and "overtrading" not in trade["tags"]:
                        trade["tags"].append("overtrading")


def _avg(rows: list[dict[str, Any]], key: str) -> float:
    vals = [r[key] for r in rows]
    return round(statistics.mean(vals), 4) if vals else 0.0


def _aggregate(run_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    all_trades = [t for r in run_summaries for t in r["trades"]]
    losers = [t for t in all_trades if t["is_loss"]]
    winners = [t for t in all_trades if not t["is_loss"]]

    tag_counts = Counter(tag for t in losers for tag in t["tags"])
    largest_losses = sorted(losers, key=lambda t: t["pnl"])[:15]

    strategy_contribution: dict[str, Any] = {}
    for name in _STRATEGY_NAMES:
        loser_agree = [1.0 if name in t["agreeing_strategies_entry"] else 0.0 for t in losers]
        winner_agree = [1.0 if name in t["agreeing_strategies_entry"] else 0.0 for t in winners]
        loser_rate = statistics.mean(loser_agree) if loser_agree else 0.0
        winner_rate = statistics.mean(winner_agree) if winner_agree else 0.0
        strategy_contribution[name] = {
            "agree_rate_on_losers": round(loser_rate, 4),
            "agree_rate_on_winners": round(winner_rate, 4),
            "delta": round(loser_rate - winner_rate, 4),
        }

    fusion_contribution = {
        "avg_entry_consensus_losers": _avg(losers, "entry_vote_agree_frac"),
        "avg_entry_consensus_winners": _avg(winners, "entry_vote_agree_frac"),
        "avg_exit_consensus_losers": _avg(losers, "exit_vote_agree_frac"),
        "avg_exit_consensus_winners": _avg(winners, "exit_vote_agree_frac"),
    }

    return {
        "total_trades": len(all_trades), "losing_trades": len(losers), "winning_trades": len(winners),
        "loss_rate_pct": round(len(losers) / len(all_trades) * 100, 2) if all_trades else 0.0,
        "largest_losses": largest_losses,
        "repeated_failure_patterns": {
            tag: {"count": count, "pct_of_losers": round(count / len(losers) * 100, 2) if losers else 0.0}
            for tag, count in tag_counts.most_common()
        },
        "avg_mae_pct_losers": _avg(losers, "mae_pct"), "avg_mae_pct_winners": _avg(winners, "mae_pct"),
        "avg_mfe_pct_losers": _avg(losers, "mfe_pct"), "avg_mfe_pct_winners": _avg(winners, "mfe_pct"),
        "avg_holding_bars_losers": _avg(losers, "holding_bars"), "avg_holding_bars_winners": _avg(winners, "holding_bars"),
        "avg_entry_timing_pct_losers": _avg(losers, "entry_timing_pct"),
        "avg_entry_timing_pct_winners": _avg(winners, "entry_timing_pct"),
        "avg_exit_timing_pct_losers": _avg(losers, "exit_timing_pct"),
        "avg_exit_timing_pct_winners": _avg(winners, "exit_timing_pct"),
        "strategy_contribution": strategy_contribution,
        "fusion_contribution": fusion_contribution,
        "overtrading_flagged_runs": [
            {
                "symbol": r["symbol"], "timeframe": r["timeframe"], "source": r["source"],
                "trades_per_100_bars": r["trades_per_100_bars"], "avg_holding_time_bars": r["avg_holding_time_bars"],
            }
            for r in run_summaries if r.get("overtrading_flagged")
        ],
    }


async def run_full_loss_attribution_study() -> dict[str, Any]:
    """Run the complete Sprint 7 study and return the full results bundle."""
    started_at = time.time()

    real_runs = await _run_real_data()
    synthetic_runs = await _run_synthetic_data()
    all_runs = real_runs + synthetic_runs
    _flag_overtrading(all_runs)

    aggregate_combined = _aggregate(all_runs)
    aggregate_real = _aggregate(real_runs)
    aggregate_synthetic = _aggregate(synthetic_runs)

    return {
        "started_at": started_at, "completed_at": time.time(),
        "real_symbols": REAL_SYMBOLS, "synthetic_symbols": SYMBOLS, "timeframes": list(TIMEFRAMES),
        "run_summaries": [{k: v for k, v in r.items() if k != "trades"} for r in all_runs],
        "aggregate_combined": aggregate_combined,
        "aggregate_real_only": aggregate_real,
        "aggregate_synthetic_only": aggregate_synthetic,
    }
