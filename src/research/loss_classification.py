"""Sprint 7 — Per-trade loss classification and forensic metrics.

Post-hoc analysis only: computes Maximum Adverse/Favorable Excursion,
entry/exit timing quality, and regime-based failure-pattern tags from
the bars and closed trades an already-completed (frozen-logic)
backtest produced. Nothing here changes what was traded, generates a
signal, or touches Decision Fusion — it only explains, after the fact,
trades that already happened. No new indicator or strategy is
introduced: every metric here is plain arithmetic over OHLCV prices
already present in the (frozen) ``HistoricalBar`` series.

All trades in this codebase are long-only (``PaperBroker`` has no
shorting), so every formula below is long-only by construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backtesting.data import HistoricalBar
from backtesting.metrics import ClosedTrade
from research.regime import HIGH_VOLATILITY, SIDEWAYS, TRENDING_BULL, detect_regimes

_TIMING_WINDOW = 5  # bars examined around entry/exit for timing-quality scoring
_DELAYED_THRESHOLD_PCT = 1.0  # entry/exit timing worse than this (%) is tagged "delayed"


@dataclass
class TradeForensics:
    """Full forensic record for one closed trade."""

    symbol: str
    timeframe: str
    source: str  # "binance" | "synthetic"
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    is_loss: bool
    holding_bars: int
    mae_pct: float           # magnitude: worst adverse move from entry, as % of entry price
    mfe_pct: float           # magnitude: best favorable move from entry, as % of entry price
    entry_timing_pct: float  # 0 = bought at the local low; higher = bought further above it (worse)
    exit_timing_pct: float   # 0 = sold at the local high; higher = sold further below it (worse)
    entry_regime: str
    exit_regime: str
    regime_changed: bool
    entry_vote_agree_frac: float  # fraction of the 8 strategies that voted BUY at entry
    exit_vote_agree_frac: float   # fraction of the 8 strategies that voted SELL at exit
    agreeing_strategies_entry: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def compute_trade_forensics(
    symbol: str,
    timeframe: str,
    source: str,
    bars: list[HistoricalBar],
    trades: list[ClosedTrade],
    per_bar_strategy_directions: dict[str, list[str]],
    per_bar_fused_direction: list[str],
) -> list[TradeForensics]:
    """Build a ``TradeForensics`` record for every closed trade in ``trades``.

    Args:
        symbol, timeframe, source: labels carried through for aggregation.
        bars: the exact bar series the trades were generated from.
        trades: closed trades from a ``ForensicRun``/``BacktestReport``.
        per_bar_strategy_directions: strategy_name -> per-bar BUY/SELL/HOLD,
            aligned 1:1 with ``bars``.
        per_bar_fused_direction: unused here directly (kept for symmetry /
            future use) — the fused decision at each bar.
    """
    regimes = detect_regimes(bars)
    results: list[TradeForensics] = []
    strategy_names = list(per_bar_strategy_directions.keys())

    for trade in trades:
        entry_bar, exit_bar = trade.entry_bar, trade.exit_bar
        span = bars[entry_bar:exit_bar + 1]
        lows = [b.low for b in span] or [trade.entry_price]
        highs = [b.high for b in span] or [trade.entry_price]

        worst_low = min(lows)
        best_high = max(highs)
        mae_pct = max(0.0, (trade.entry_price - worst_low) / trade.entry_price * 100.0) if trade.entry_price else 0.0
        mfe_pct = max(0.0, (best_high - trade.entry_price) / trade.entry_price * 100.0) if trade.entry_price else 0.0

        entry_lo = max(0, entry_bar - _TIMING_WINDOW)
        entry_hi = min(len(bars), entry_bar + _TIMING_WINDOW + 1)
        local_entry_low = min(b.low for b in bars[entry_lo:entry_hi])
        entry_timing_pct = max(0.0, (trade.entry_price - local_entry_low) / trade.entry_price * 100.0) if trade.entry_price else 0.0

        exit_lo = max(0, exit_bar - _TIMING_WINDOW)
        exit_hi = min(len(bars), exit_bar + _TIMING_WINDOW + 1)
        local_exit_high = max(b.high for b in bars[exit_lo:exit_hi])
        exit_timing_pct = max(0.0, (local_exit_high - trade.exit_price) / local_exit_high * 100.0) if local_exit_high else 0.0

        entry_regime = regimes[entry_bar] if entry_bar < len(regimes) else SIDEWAYS
        exit_regime = regimes[exit_bar] if exit_bar < len(regimes) else SIDEWAYS

        agreeing_entry = [
            name for name in strategy_names
            if entry_bar < len(per_bar_strategy_directions[name]) and per_bar_strategy_directions[name][entry_bar] == "BUY"
        ]
        agreeing_exit = [
            name for name in strategy_names
            if exit_bar < len(per_bar_strategy_directions[name]) and per_bar_strategy_directions[name][exit_bar] == "SELL"
        ]
        entry_vote_agree_frac = len(agreeing_entry) / len(strategy_names) if strategy_names else 0.0
        exit_vote_agree_frac = len(agreeing_exit) / len(strategy_names) if strategy_names else 0.0

        pnl_pct = (trade.exit_price - trade.entry_price) / trade.entry_price * 100.0 if trade.entry_price else 0.0
        is_loss = trade.pnl <= 0

        tags: list[str] = []
        if is_loss:
            if entry_regime == TRENDING_BULL and exit_regime != TRENDING_BULL:
                tags.append("trend_reversal")
            if entry_regime == SIDEWAYS or exit_regime == SIDEWAYS:
                tags.append("ranging_market")
            if entry_regime == HIGH_VOLATILITY or exit_regime == HIGH_VOLATILITY:
                tags.append("volatility_spike")
            if entry_timing_pct > _DELAYED_THRESHOLD_PCT:
                tags.append("delayed_entry")
            if exit_timing_pct > _DELAYED_THRESHOLD_PCT:
                tags.append("delayed_exit")

        results.append(
            TradeForensics(
                symbol=symbol, timeframe=timeframe, source=source,
                entry_bar=entry_bar, exit_bar=exit_bar,
                entry_price=trade.entry_price, exit_price=trade.exit_price,
                pnl=round(trade.pnl, 4), pnl_pct=round(pnl_pct, 4), is_loss=is_loss,
                holding_bars=exit_bar - entry_bar,
                mae_pct=round(mae_pct, 4), mfe_pct=round(mfe_pct, 4),
                entry_timing_pct=round(entry_timing_pct, 4), exit_timing_pct=round(exit_timing_pct, 4),
                entry_regime=entry_regime, exit_regime=exit_regime,
                regime_changed=(entry_regime != exit_regime),
                entry_vote_agree_frac=round(entry_vote_agree_frac, 4),
                exit_vote_agree_frac=round(exit_vote_agree_frac, 4),
                agreeing_strategies_entry=agreeing_entry, tags=tags,
            )
        )

    return results
