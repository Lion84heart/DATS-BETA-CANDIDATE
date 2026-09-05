"""ATR-based Stop Loss, Trailing Stop, and Break-even Protection
(Phase 4, modules 3, 4, 5).

Pure price-level calculators over a trade's own entry price, ATR at
entry, and the highest price reached since entry (``peak_price``,
tracked by the caller). None of this generates a trading signal or
touches Decision Fusion — each function only computes a price level;
the caller (``execution_intelligence.managed_backtest``) checks
whether a bar's low breached it and, if so, exits.
"""

from __future__ import annotations

from dataclasses import dataclass

_DEFAULT_ATR_STOP_MULT = 2.0
_DEFAULT_TRAILING_ATR_MULT = 2.5
_DEFAULT_BREAKEVEN_TRIGGER_PCT = 1.5   # once unrealized gain reaches this %, arm break-even
_DEFAULT_BREAKEVEN_BUFFER_PCT = 0.1    # breakeven stop sits this % above entry (covers commission/slippage)
_DEFAULT_TAKE_PROFIT_ATR_MULT = 3.0    # symmetric upside counterpart to the ATR stop


@dataclass
class StopState:
    """Per-trade mutable state the exit engine tracks across bars."""

    entry_price: float
    atr_at_entry: float | None
    peak_price: float
    breakeven_armed: bool = False


def initial_atr_stop_price(
    entry_price: float, atr_at_entry: float | None, mult: float = _DEFAULT_ATR_STOP_MULT,
) -> float | None:
    """A fixed stop, set once at entry and never moved — module 3."""
    if atr_at_entry is None or atr_at_entry <= 0:
        return None
    return entry_price - mult * atr_at_entry


def trailing_stop_price(state: StopState, mult: float = _DEFAULT_TRAILING_ATR_MULT) -> float | None:
    """Ratchets up with ``state.peak_price`` — module 4."""
    if state.atr_at_entry is None or state.atr_at_entry <= 0:
        return None
    return state.peak_price - mult * state.atr_at_entry


def breakeven_stop_price(
    state: StopState,
    current_price: float,
    trigger_pct: float = _DEFAULT_BREAKEVEN_TRIGGER_PCT,
    buffer_pct: float = _DEFAULT_BREAKEVEN_BUFFER_PCT,
) -> float | None:
    """Once unrealized gain reaches ``trigger_pct``, arms a stop just
    above entry (module 5) so the worst case for the trade becomes a
    small, near-zero loss instead of the full stop-loss distance.
    Arming is monotonic — mutates ``state.breakeven_armed`` and never
    un-arms once triggered.
    """
    gain_pct = (current_price - state.entry_price) / state.entry_price * 100.0 if state.entry_price else 0.0
    if gain_pct >= trigger_pct:
        state.breakeven_armed = True
    if not state.breakeven_armed:
        return None
    return state.entry_price * (1.0 + buffer_pct / 100.0)


def take_profit_price(
    entry_price: float, atr_at_entry: float | None, mult: float = _DEFAULT_TAKE_PROFIT_ATR_MULT,
) -> float | None:
    """A fixed upside target, set once at entry and never moved — the
    symmetric counterpart to ``initial_atr_stop_price``. Not part of
    Phase 4's original module set; added when the live paper-trading
    pipeline needed a genuine "Take Profit" value to record per trade,
    reusing the identical ATR-multiple pattern already used for the
    stop loss rather than inventing a new mechanism.
    """
    if atr_at_entry is None or atr_at_entry <= 0:
        return None
    return entry_price + mult * atr_at_entry
