"""Standalone ATR computation for trade-management purposes (Phase 4).

This is NOT a trading strategy — it never generates a BUY/SELL/HOLD
signal and never feeds Decision Fusion. It's risk-management plumbing
(stop-loss distance, position sizing) that reuses the same standard
True-Range rolling-average formula ``trading.strategies.atr.ATRStrategy``
already computes internally for its own, frozen, unmodified signal
generation. Computing ATR here for a different purpose doesn't touch
that file and doesn't add a ninth strategy to the Strategy Engine.
"""

from __future__ import annotations

from backtesting.data import HistoricalBar

_DEFAULT_PERIOD = 14


def compute_atr(bars: list[HistoricalBar], period: int = _DEFAULT_PERIOD) -> float | None:
    """True Range rolling average over the trailing ``period`` bars
    ending at the last bar in ``bars``.

    Returns:
        The ATR value, or ``None`` if there isn't enough history yet
        (mirrors the frozen ``ATRStrategy``'s own insufficient-history
        handling — an honest "not available" rather than a fabricated 0).
    """
    if len(bars) < period + 1:
        return None
    trs: list[float] = []
    for i in range(len(bars) - period, len(bars)):
        high, low = bars[i].high, bars[i].low
        prev_close = bars[i - 1].close
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs) / len(trs)
