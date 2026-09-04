"""Dynamic Exit Engine (Phase 4, module 2).

Combines the ATR-based stop loss, trailing stop, and break-even
protection (``stops.py``) with the frozen Decision Fusion's own SELL
signal into one per-bar exit decision — whichever fires first, this
bar, wins. Priority order: hard ATR stop first (protects against the
largest adverse moves), then break-even, then trailing, then the fused
SELL signal last (the baseline's own — and only — trigger, preserved
as the final fallback). With all three stop mechanisms disabled, this
reduces to exactly the baseline's fused-SELL-only behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

from execution_intelligence.stops import (
    StopState,
    breakeven_stop_price,
    initial_atr_stop_price,
    trailing_stop_price,
)


@dataclass
class ExitDecision:
    should_exit: bool
    reason: str  # "fused_sell" | "atr_stop" | "trailing_stop" | "breakeven_stop" | "none"
    trigger_price: float | None = None


class DynamicExitEngine:
    def __init__(
        self,
        use_atr_stop: bool = True,
        use_trailing_stop: bool = True,
        use_breakeven: bool = True,
        atr_stop_mult: float = 2.0,
        trailing_mult: float = 2.5,
        breakeven_trigger_pct: float = 1.5,
        breakeven_buffer_pct: float = 0.1,
    ) -> None:
        self.use_atr_stop = use_atr_stop
        self.use_trailing_stop = use_trailing_stop
        self.use_breakeven = use_breakeven
        self.atr_stop_mult = atr_stop_mult
        self.trailing_mult = trailing_mult
        self.breakeven_trigger_pct = breakeven_trigger_pct
        self.breakeven_buffer_pct = breakeven_buffer_pct

    def check_bar(
        self, state: StopState, bar_low: float, bar_high: float, fused_sell: bool,
    ) -> ExitDecision:
        state.peak_price = max(state.peak_price, bar_high)

        if self.use_atr_stop:
            atr_stop = initial_atr_stop_price(state.entry_price, state.atr_at_entry, self.atr_stop_mult)
            if atr_stop is not None and bar_low <= atr_stop:
                return ExitDecision(True, "atr_stop", atr_stop)

        if self.use_breakeven:
            be_stop = breakeven_stop_price(state, bar_high, self.breakeven_trigger_pct, self.breakeven_buffer_pct)
            if be_stop is not None and bar_low <= be_stop:
                return ExitDecision(True, "breakeven_stop", be_stop)

        if self.use_trailing_stop:
            tr_stop = trailing_stop_price(state, self.trailing_mult)
            if tr_stop is not None and bar_low <= tr_stop:
                return ExitDecision(True, "trailing_stop", tr_stop)

        if fused_sell:
            return ExitDecision(True, "fused_sell", None)

        return ExitDecision(False, "none", None)
