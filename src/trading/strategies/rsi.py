"""DATS — RSI (Relative Strength Index) Strategy.

Classic momentum oscillator. RSI < 30 is read as oversold (BUY), RSI > 70
as overbought (SELL), otherwise HOLD. Confidence scales with distance
past the threshold. No LLM/external AI — a deterministic formula over
real close-price history.
"""

from __future__ import annotations

import pandas as pd

from trading.base_strategy import BaseStrategy
from trading.schemas import SignalDirection, StrategySignal, StrategyType

_DEFAULT_PERIOD = 14
_OVERSOLD = 30.0
_OVERBOUGHT = 70.0


class RSIStrategy(BaseStrategy):
    """RSI(14) mean-reversion signal. Always returns a signal (BUY/SELL/HOLD)."""

    name = "rsi"
    strategy_type = StrategyType.MEAN_REVERSION

    def _apply_defaults(self) -> None:
        if "period" not in self.parameters:
            self.parameters["period"] = float(_DEFAULT_PERIOD)
        self.config.parameters = dict(self.parameters)

    def parameter_bounds(self) -> dict[str, tuple[float, float]]:
        return {"period": (5.0, 30.0)}

    def generate_signal(
        self,
        ohlcv_df: pd.DataFrame,
        features: dict[str, float | None],
    ) -> StrategySignal:
        period = int(self.parameters.get("period", _DEFAULT_PERIOD))

        if ohlcv_df.empty or len(ohlcv_df) < period + 1:
            return self._create_signal(
                direction=SignalDirection.HOLD,
                confidence=0.1,
                reason=f"RSI: only {len(ohlcv_df)}/{period + 1} bars available — insufficient history.",
                features=features,
            )

        close = ohlcv_df["close"]
        delta = close.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = gain.rolling(window=period).mean().iloc[-1]
        avg_loss = loss.rolling(window=period).mean().iloc[-1]

        if avg_loss == 0:
            rsi = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        if rsi < _OVERSOLD:
            direction = SignalDirection.BUY
            confidence = 0.5 + 0.5 * min(1.0, (_OVERSOLD - rsi) / _OVERSOLD)
            reason = f"RSI={rsi:.1f} is below the oversold threshold ({_OVERSOLD:.0f}) — mean-reversion BUY."
        elif rsi > _OVERBOUGHT:
            direction = SignalDirection.SELL
            confidence = 0.5 + 0.5 * min(1.0, (rsi - _OVERBOUGHT) / (100.0 - _OVERBOUGHT))
            reason = f"RSI={rsi:.1f} is above the overbought threshold ({_OVERBOUGHT:.0f}) — mean-reversion SELL."
        else:
            direction = SignalDirection.HOLD
            # Confidence in "no trade" is highest at RSI=50, fading toward the bands.
            confidence = 0.3 + 0.3 * (1.0 - abs(rsi - 50.0) / (_OVERBOUGHT - 50.0))
            reason = f"RSI={rsi:.1f} is inside the neutral band ({_OVERSOLD:.0f}-{_OVERBOUGHT:.0f}) — holding."

        return self._create_signal(
            direction=direction,
            confidence=self._clamp_confidence(confidence),
            reason=reason,
            features=features,
        )
