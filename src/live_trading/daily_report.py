"""Daily (and arbitrary-period) reporting for the live paper-trading log.

Reads only from ``LiveTradeStore`` — no new indicator, no new strategy,
no new dashboard. Computes exactly the fields the mission asked for.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from typing import Any

from live_trading.trade_log import LiveTradeStore


def _day_bounds_utc(date: datetime) -> tuple[float, float]:
    start = datetime(date.year, date.month, date.day, tzinfo=timezone.utc)
    end = start.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    return start.timestamp(), (end + timedelta(days=1)).timestamp()


def _max_drawdown_pct(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak)
    return round(max_dd * 100.0, 4)


def generate_report(store: LiveTradeStore, start_ts: float, end_ts: float, current_equity: float | None = None) -> dict[str, Any]:
    """Build a report for ``[start_ts, end_ts)`` — one calendar day, or
    any other window (e.g. a full week) a caller wants to pass."""
    trades = [t for t in store.get_trades_between(start_ts, end_ts) if t["status"] == "CLOSED"]
    closed_count = len(trades)

    wins = [t for t in trades if (t["pnl"] or 0.0) > 0]
    losses = [t for t in trades if (t["pnl"] or 0.0) <= 0]
    win_rate_pct = round(len(wins) / closed_count * 100.0, 2) if closed_count else 0.0

    gross_profit = round(sum(t["pnl"] for t in wins), 4) if wins else 0.0
    gross_loss = round(sum(t["pnl"] for t in losses), 4) if losses else 0.0
    net_profit = round(gross_profit + gross_loss, 4)
    fees = round(sum(t.get("fees") or 0.0 for t in trades), 4)
    average_trade = round(statistics.mean(t["pnl"] for t in trades), 4) if trades else 0.0
    largest_win = round(max((t["pnl"] for t in wins), default=0.0), 4)
    largest_loss = round(min((t["pnl"] for t in losses), default=0.0), 4)

    equity_rows = store.get_equity_curve_between(start_ts, end_ts)
    equity_curve = [r["equity"] for r in equity_rows]
    max_drawdown_pct = _max_drawdown_pct(equity_curve) if equity_curve else 0.0

    open_trades = store.get_open_trades()

    return {
        "window_start_utc": datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat(),
        "window_end_utc": datetime.fromtimestamp(end_ts, tz=timezone.utc).isoformat(),
        "number_of_trades": closed_count,
        "win_rate_pct": win_rate_pct,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_profit": net_profit,
        "fees": fees,
        "average_trade": average_trade,
        "largest_win": largest_win,
        "largest_loss": largest_loss,
        "current_equity": round(current_equity, 4) if current_equity is not None else (equity_curve[-1] if equity_curve else None),
        "max_drawdown_pct": max_drawdown_pct,
        "open_positions": open_trades,
        "open_position_count": len(open_trades),
    }


def generate_daily_report(store: LiveTradeStore, date: datetime, current_equity: float | None = None) -> dict[str, Any]:
    start_ts, end_ts = _day_bounds_utc(date)
    return generate_report(store, start_ts, end_ts, current_equity)
