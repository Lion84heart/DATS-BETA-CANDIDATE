"""DATS — ATR (Average True Range) Breakout Strategy.

ATR measures recent volatility (not direction). This strategy turns it
into a signal via a volatility breakout: BUY when price has moved up
more than a multiple of ATR from N bars ago, SELL on the symmetric
downside breakout, HOLD otherwise. No LLM/external AI — a deterministic
formula over real OHLC data.

Note: the True Range formula uses high/low/close as given. The engine's
current tick-derived bars set high=low=close=the tick price (no
intrabar range is available from a single price tick), so ATR here
reduces to the average absolute close-to-close move — a standard,
honest simplification, not a fabricated number. The formula is written
against the full high/low/close definition so it would automatically
use real intrabar range if the engine is ever fed true OHLC bars.
"""

from __future__ import annotations

import pandas as pd

from trading.base_strategy import BaseStrategy
from trading.schemas import SignalDirection, StrategySignal, StrategyType

_DEFAULT_PERIOD = 14
_DEFAULT_BREAKOUT_MULT = 1.5
_DEFAULT_LOOKBACK = 10


class ATRStrategy(BaseStrategy):
    """ATR-based volatility breakout signal. Always returns a signal."""

    name = "atr"
    strategy_type = StrategyType.BREAKOUT

    def _apply_defaults(self) -> None:
        defaults = {
            "period": float(_DEFAULT_PERIOD),
            "breakout_mult": _DEFAULT_BREAKOUT_MULT,
            "lookback": float(_DEFAULT_LOOKBACK),
        }
        for key, value in defaults.items():
            if key not in self.parameters:
                self.parameters[key] = value
        self.config.parameters = dict(self.parameters)

    def parameter_bounds(self) -> dict[str, tuple[float, float]]:
        return {"period": (5.0, 30.0), "breakout_mult": (0.5, 4.0), "lookback": (3.0, 30.0)}

    def generate_signal(
        self,
        ohlcv_df: pd.DataFrame,
        features: dict[str, float | None],
    ) -> StrategySignal:
        period = int(self.parameters.get("period", _DEFAULT_PERIOD))
        mult = self.parameters.get("breakout_mult", _DEFAULT_BREAKOUT_MULT)
        lookback = int(self.parameters.get("lookback", _DEFAULT_LOOKBACK))
        min_bars = period + lookback + 1

        if ohlcv_df.empty or len(ohlcv_df) < min_bars:
            return self._create_signal(
                direction=SignalDirection.HOLD,
                confidence=0.1,
                reason=f"ATR: only {len(ohlcv_df)}/{min_bars} bars available — insufficient history.",
                features=features,
            )

        high, low, close = ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"]
        prev_close = close.shift(1)
        true_range = pd.concat(
            [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
        ).max(axis=1)
        atr = float(true_range.rolling(window=period).mean().iloc[-1])

        close_now = float(close.iloc[-1])
        close_ref = float(close.iloc[-1 - lookback])
        move = close_now - close_ref

        if atr <= 0:
            return self._create_signal(
                direction=SignalDirection.HOLD,
                confidence=0.2,
                reason="ATR is zero over the lookback window — no volatility to measure a breakout against.",
                features=features,
            )

        move_in_atr = move / atr

        if move_in_atr >= mult:
            direction = SignalDirection.BUY
            confidence = 0.5 + 0.5 * min(1.0, (move_in_atr - mult) / mult)
            reason = (
                f"Price moved +{move_in_atr:.2f}x ATR (${atr:.4f}) over the last {lookback} bars — "
                f"upside volatility breakout."
            )
        elif move_in_atr <= -mult:
            direction = SignalDirection.SELL
            confidence = 0.5 + 0.5 * min(1.0, (abs(move_in_atr) - mult) / mult)
            reason = (
                f"Price moved {move_in_atr:.2f}x ATR (${atr:.4f}) over the last {lookback} bars — "
                f"downside volatility breakout."
            )
        else:
            direction = SignalDirection.HOLD
            confidence = 0.2 + 0.3 * (1.0 - min(1.0, abs(move_in_atr) / mult))
            reason = f"Price move ({move_in_atr:.2f}x ATR) is below the {mult:.1f}x breakout threshold — holding."

        return self._create_signal(
            direction=direction,
            confidence=self._clamp_confidence(confidence),
            reason=reason,
            features=features,
        )
