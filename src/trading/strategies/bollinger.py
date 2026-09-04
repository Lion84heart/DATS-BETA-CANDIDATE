"""DATS — Bollinger Bands Strategy.

SMA(20) with +/-2 standard-deviation bands. BUY when price touches or
crosses below the lower band (oversold), SELL at/above the upper band
(overbought), HOLD inside the bands. Confidence uses %B, the position
of price within the band. No LLM/external AI — a deterministic formula
over real close-price history.
"""

from __future__ import annotations

import pandas as pd

from trading.base_strategy import BaseStrategy
from trading.schemas import SignalDirection, StrategySignal, StrategyType

_DEFAULT_PERIOD = 20
_DEFAULT_NUM_STD = 2.0


class BollingerBandsStrategy(BaseStrategy):
    """Bollinger Bands mean-reversion signal. Always returns a signal."""

    name = "bollinger_bands"
    strategy_type = StrategyType.MEAN_REVERSION

    def _apply_defaults(self) -> None:
        defaults = {"period": float(_DEFAULT_PERIOD), "num_std": _DEFAULT_NUM_STD}
        for key, value in defaults.items():
            if key not in self.parameters:
                self.parameters[key] = value
        self.config.parameters = dict(self.parameters)

    def parameter_bounds(self) -> dict[str, tuple[float, float]]:
        return {"period": (10.0, 50.0), "num_std": (1.0, 3.5)}

    def generate_signal(
        self,
        ohlcv_df: pd.DataFrame,
        features: dict[str, float | None],
    ) -> StrategySignal:
        period = int(self.parameters.get("period", _DEFAULT_PERIOD))
        num_std = self.parameters.get("num_std", _DEFAULT_NUM_STD)

        if ohlcv_df.empty or len(ohlcv_df) < period:
            return self._create_signal(
                direction=SignalDirection.HOLD,
                confidence=0.1,
                reason=f"Bollinger Bands: only {len(ohlcv_df)}/{period} bars available — insufficient history.",
                features=features,
            )

        close = ohlcv_df["close"]
        sma = close.rolling(window=period).mean().iloc[-1]
        std = close.rolling(window=period).std().iloc[-1]
        close_now = float(close.iloc[-1])

        if pd.isna(sma) or pd.isna(std) or std == 0:
            return self._create_signal(
                direction=SignalDirection.HOLD,
                confidence=0.2,
                reason="Bollinger Bands: zero recent volatility — bands are degenerate, holding.",
                features=features,
            )

        upper = float(sma + num_std * std)
        lower = float(sma - num_std * std)
        percent_b = (close_now - lower) / (upper - lower) if upper != lower else 0.5

        if close_now <= lower:
            direction = SignalDirection.BUY
            confidence = 0.5 + 0.5 * min(1.0, (lower - close_now) / (num_std * std))
            reason = f"Price ${close_now:.2f} is at/below the lower band ${lower:.2f} (%B={percent_b:.2f}) — oversold BUY."
        elif close_now >= upper:
            direction = SignalDirection.SELL
            confidence = 0.5 + 0.5 * min(1.0, (close_now - upper) / (num_std * std))
            reason = f"Price ${close_now:.2f} is at/above the upper band ${upper:.2f} (%B={percent_b:.2f}) — overbought SELL."
        else:
            direction = SignalDirection.HOLD
            confidence = 0.2 + 0.3 * (1.0 - abs(percent_b - 0.5) * 2)
            reason = f"Price ${close_now:.2f} is inside the bands [${lower:.2f}, ${upper:.2f}] (%B={percent_b:.2f}) — holding."

        return self._create_signal(
            direction=direction,
            confidence=self._clamp_confidence(confidence),
            reason=reason,
            features=features,
        )
