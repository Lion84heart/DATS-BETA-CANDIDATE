"""Portfolio performance metrics for a completed backtest run.

Standard, well-known formulas. Each bar is treated as one trading day
for annualization purposes (252 bars/year) — the Strategy Engine's live
pipeline has no inherent bar-to-calendar-time mapping of its own, so
this is a documented convention, not an assumption hidden in the math.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

_BARS_PER_YEAR = 252


@dataclass(frozen=True)
class ClosedTrade:
    """A completed round-trip (entry + exit) trade from the backtest."""

    symbol: str
    entry_time: float
    exit_time: float
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    commission: float


@dataclass
class PortfolioMetrics:
    """The eleven required backtest evaluation metrics."""

    total_return_pct: float = 0.0
    cagr_pct: float = 0.0
    win_rate_pct: float = 0.0
    profit_factor: float | None = None  # None represents "infinite" (no losing trades)
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    average_trade_pnl: float = 0.0
    average_hold_time_bars: float = 0.0
    exposure_pct: float = 0.0
    number_of_trades: int = 0


def compute_portfolio_metrics(
    equity_curve: list[float],
    trades: list[ClosedTrade],
    num_bars: int,
    bars_in_position: int,
    initial_capital: float,
    bars_per_year: int = _BARS_PER_YEAR,
) -> PortfolioMetrics:
    """Compute the full set of portfolio evaluation metrics.

    Args:
        equity_curve: Mark-to-market portfolio value, one entry per bar,
            with the initial capital as the first entry.
        trades: Every closed round-trip trade.
        num_bars: Total bars replayed.
        bars_in_position: Bars during which a position was held.
        initial_capital: Starting capital.
        bars_per_year: Bars treated as one year for annualization.

    Returns:
        PortfolioMetrics with all eleven required fields populated.
    """
    if not equity_curve:
        equity_curve = [initial_capital]
    final_equity = equity_curve[-1]

    total_return_pct = (
        (final_equity - initial_capital) / initial_capital * 100.0 if initial_capital > 0 else 0.0
    )

    years = num_bars / bars_per_year if bars_per_year else 0.0
    if years > 0 and initial_capital > 0 and final_equity > 0:
        cagr_pct = ((final_equity / initial_capital) ** (1.0 / years) - 1.0) * 100.0
    else:
        cagr_pct = 0.0

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate_pct = (len(wins) / len(trades) * 100.0) if trades else 0.0

    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    if gross_loss > 0:
        profit_factor: float | None = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = None  # no losing trades — "infinite" profit factor
    else:
        profit_factor = 0.0

    eq = np.array(equity_curve, dtype=float)
    returns = np.diff(eq) / eq[:-1] if len(eq) > 1 else np.array([])
    returns = returns[np.isfinite(returns)]

    if len(returns) > 1 and returns.std() > 0:
        sharpe_ratio = float(returns.mean() / returns.std() * math.sqrt(bars_per_year))
    else:
        sharpe_ratio = 0.0

    downside = returns[returns < 0]
    if len(downside) > 0 and downside.std() > 0:
        sortino_ratio = float(returns.mean() / downside.std() * math.sqrt(bars_per_year))
    else:
        sortino_ratio = 0.0

    peak = eq[0] if len(eq) else initial_capital
    max_dd = 0.0
    for v in eq:
        if v > peak:
            peak = v
        elif peak > 0:
            dd = (peak - v) / peak
            max_dd = max(max_dd, dd)
    max_drawdown_pct = max_dd * 100.0

    average_trade_pnl = (sum(t.pnl for t in trades) / len(trades)) if trades else 0.0
    average_hold_time_bars = (
        sum(t.exit_bar - t.entry_bar for t in trades) / len(trades) if trades else 0.0
    )
    exposure_pct = (bars_in_position / num_bars * 100.0) if num_bars else 0.0

    return PortfolioMetrics(
        total_return_pct=round(total_return_pct, 4),
        cagr_pct=round(cagr_pct, 4),
        win_rate_pct=round(win_rate_pct, 2),
        profit_factor=round(profit_factor, 4) if profit_factor is not None else None,
        sharpe_ratio=round(sharpe_ratio, 4),
        sortino_ratio=round(sortino_ratio, 4),
        max_drawdown_pct=round(max_drawdown_pct, 4),
        average_trade_pnl=round(average_trade_pnl, 4),
        average_hold_time_bars=round(average_hold_time_bars, 2),
        exposure_pct=round(exposure_pct, 2),
        number_of_trades=len(trades),
    )
