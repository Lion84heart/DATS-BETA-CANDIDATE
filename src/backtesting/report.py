"""Serialization of a BacktestReport to plain dicts, JSON, and CSV."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict
from typing import Any

from backtesting.engine import BacktestReport


def report_to_dict(report: BacktestReport) -> dict[str, Any]:
    """Convert a BacktestReport into a fully JSON-serializable dict."""
    return {
        "run_id": report.run_id,
        "symbol": report.symbol,
        "started_at": report.started_at,
        "completed_at": report.completed_at,
        "num_bars": report.num_bars,
        "initial_capital": report.initial_capital,
        "final_equity": report.final_equity,
        "portfolio_metrics": asdict(report.portfolio_metrics),
        "fusion_confusion": asdict(report.fusion_confusion),
        "per_strategy_stats": [
            {
                "strategy": s.strategy,
                "buy_count": s.buy_count,
                "sell_count": s.sell_count,
                "hold_count": s.hold_count,
                "avg_confidence": s.avg_confidence,
                "confusion": asdict(s.confusion) if s.confusion else None,
            }
            for s in report.per_strategy_stats
        ],
        "trades": [asdict(t) for t in report.trades],
        "equity_curve": report.equity_curve,
        "decisions": report.decisions,
    }


def report_to_json(report: BacktestReport, indent: int | None = 2) -> str:
    """Serialize a BacktestReport to a JSON string."""
    return json.dumps(report_to_dict(report), indent=indent, default=str)


def dict_to_csv(data: dict[str, Any]) -> str:
    """Serialize a (JSON-shaped) backtest report dict into one CSV file.

    A backtest report has several distinct tabular sections (summary
    metrics, per-strategy stats, trades) that don't share one row shape,
    so this produces a single CSV with clearly labeled sections rather
    than forcing everything into one flat table.
    """
    buf = io.StringIO()

    buf.write(f"# Backtest Report — {data['run_id']}\n")
    buf.write(f"# Symbol: {data['symbol']}\n")
    buf.write(f"# Bars: {data['num_bars']}\n")
    buf.write(f"# Initial Capital: {data['initial_capital']}\n")
    buf.write(f"# Final Equity: {data['final_equity']}\n\n")

    buf.write("## PORTFOLIO METRICS\n")
    writer = csv.writer(buf)
    writer.writerow(["metric", "value"])
    for key, value in data["portfolio_metrics"].items():
        writer.writerow([key, value])
    buf.write("\n")

    buf.write("## FUSION CONFUSION MATRIX (predicted signal vs. actual subsequent move)\n")
    fc = data["fusion_confusion"]
    writer.writerow(["predicted", "actual_up", "actual_down", "actual_flat", "precision_pct", "support"])
    for predicted in ("BUY", "SELL", "HOLD"):
        row = fc["matrix"].get(predicted, {})
        writer.writerow([
            predicted, row.get("UP", 0), row.get("DOWN", 0), row.get("FLAT", 0),
            fc["precision_pct"].get(predicted, 0), fc["support"].get(predicted, 0),
        ])
    buf.write("\n")

    buf.write("## PER-STRATEGY STATISTICS\n")
    writer.writerow(["strategy", "buy_count", "sell_count", "hold_count", "avg_confidence", "precision_pct_buy", "precision_pct_sell", "precision_pct_hold"])
    for s in data["per_strategy_stats"]:
        prec = (s["confusion"] or {}).get("precision_pct", {})
        writer.writerow([
            s["strategy"], s["buy_count"], s["sell_count"], s["hold_count"], s["avg_confidence"],
            prec.get("BUY", 0), prec.get("SELL", 0), prec.get("HOLD", 0),
        ])
    buf.write("\n")

    buf.write("## TRADES\n")
    if data["trades"]:
        writer.writerow(list(data["trades"][0].keys()))
        for t in data["trades"]:
            writer.writerow(list(t.values()))
    else:
        buf.write("(no trades)\n")

    return buf.getvalue()
