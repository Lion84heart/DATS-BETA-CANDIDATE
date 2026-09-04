"""DATS — EMA Cross Strategy.

Fast/slow exponential moving average crossover. BUY on a bullish cross
(fast EMA moves above slow EMA this bar), SELL on a bearish cross,
HOLD when no cross occurred this bar. Confidence scales with how
recently/decisively the cross happened. No LLM/external AI — a
deterministic formula over real close-price history.
"""

from __future__ import annotations

import pandas as pd

from trading.base_strategy import BaseStrategy
from trading.schemas import SignalDirection, StrategySignal, StrategyType

_DEFAULT_FAST = 9
_DEFAULT_SLOW = 21


class EMACrossStrategy(BaseStrategy):
    """EMA(9)/EMA(21) crossover signal. Always returns a signal."""

    name = "ema_cross"
    strategy_type = StrategyType.TREND_FOLLOWING

    def _apply_defaults(self) -> None:
        defaults = {"fast_period": float(_DEFAULT_FAST), "slow_period": float(_DEFAULT_SLOW)}
        for key, value in defaults.items():
            if key not in self.parameters:
                self.parameters[key] = value
        self.config.parameters = dict(self.parameters)

    def parameter_bounds(self) -> dict[str, tuple[float, float]]:
        return {"fast_period": (3.0, 20.0), "slow_period": (10.0, 60.0)}

    def generate_signal(
        self,
        ohlcv_df: pd.DataFrame,
        features: dict[str, float | None],
    ) -> StrategySignal:
        fast_p = int(self.parameters.get("fast_period", _DEFAULT_FAST))
        slow_p = int(self.parameters.get("slow_period", _DEFAULT_SLOW))
        min_bars = slow_p + 2

        if ohlcv_df.empty or len(ohlcv_df) < min_bars:
            return self._create_signal(
                direction=SignalDirection.HOLD,
                confidence=0.1,
                reason=f"EMA Cross: only {len(ohlcv_df)}/{min_bars} bars available — insufficient history.",
                features=features,
            )

        close = ohlcv_df["close"]
        ema_fast = close.ewm(span=fast_p, adjust=False).mean()
        ema_slow = close.ewm(span=slow_p, adjust=False).mean()
        diff = ema_fast - ema_slow
        diff_now = float(diff.iloc[-1])
        diff_prev = float(diff.iloc[-2])
        slow_now = float(ema_slow.iloc[-1])
        separation_pct = abs(diff_now) / slow_now if slow_now else 0.0

        if diff_now > 0 and diff_prev <= 0:
            direction = SignalDirection.BUY
            confidence = 0.55 + 0.45 * min(1.0, separation_pct * 50)
            reason = (
                f"EMA{fast_p} crossed above EMA{slow_p} this bar "
                f"({ema_fast.iloc[-1]:.4f} vs {ema_slow.iloc[-1]:.4f}) — bullish cross."
            )
        elif diff_now < 0 and diff_prev >= 0:
            direction = SignalDirection.SELL
            confidence = 0.55 + 0.45 * min(1.0, separation_pct * 50)
            reason = (
                f"EMA{fast_p} crossed below EMA{slow_p} this bar "
                f"({ema_fast.iloc[-1]:.4f} vs {ema_slow.iloc[-1]:.4f}) — bearish cross."
            )
        else:
            direction = SignalDirection.HOLD
            confidence = 0.2 + 0.2 * (1.0 - min(1.0, separation_pct * 50))
            trend = "above" if diff_now > 0 else "below" if diff_now < 0 else "at"
            reason = f"EMA{fast_p} is {trend} EMA{slow_p} with no fresh cross this bar — holding."

        return self._create_signal(
            direction=direction,
            confidence=self._clamp_confidence(confidence),
            reason=reason,
            features=features,
        )
