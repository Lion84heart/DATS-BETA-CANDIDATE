"""DATS — VWAP (Volume Weighted Average Price) Strategy.

Compares the current close against the session's volume-weighted
average price. BUY when price is meaningfully below VWAP (potential
reversion up), SELL when meaningfully above, HOLD near VWAP. No
LLM/external AI — a deterministic formula over real price/volume data.
"""

from __future__ import annotations

import pandas as pd

from trading.base_strategy import BaseStrategy
from trading.schemas import SignalDirection, StrategySignal, StrategyType

_DEFAULT_WINDOW = 30
_DEFAULT_THRESHOLD_PCT = 0.3  # % deviation from VWAP considered significant


class VWAPStrategy(BaseStrategy):
    """VWAP deviation signal. Always returns a signal."""

    name = "vwap"
    strategy_type = StrategyType.MEAN_REVERSION

    def _apply_defaults(self) -> None:
        defaults = {"window": float(_DEFAULT_WINDOW), "threshold_pct": _DEFAULT_THRESHOLD_PCT}
        for key, value in defaults.items():
            if key not in self.parameters:
                self.parameters[key] = value
        self.config.parameters = dict(self.parameters)

    def parameter_bounds(self) -> dict[str, tuple[float, float]]:
        return {"window": (5.0, 100.0), "threshold_pct": (0.05, 2.0)}

    def generate_signal(
        self,
        ohlcv_df: pd.DataFrame,
        features: dict[str, float | None],
    ) -> StrategySignal:
        window = int(self.parameters.get("window", _DEFAULT_WINDOW))
        threshold_pct = self.parameters.get("threshold_pct", _DEFAULT_THRESHOLD_PCT)

        if ohlcv_df.empty or len(ohlcv_df) < min(window, 5):
            return self._create_signal(
                direction=SignalDirection.HOLD,
                confidence=0.1,
                reason=f"VWAP: only {len(ohlcv_df)} bars available — insufficient history.",
                features=features,
            )

        recent = ohlcv_df.tail(window)
        total_volume = float(recent["volume"].sum())
        close_now = float(recent["close"].iloc[-1])

        if total_volume <= 0:
            vwap = float(recent["close"].mean())
        else:
            vwap = float((recent["close"] * recent["volume"]).sum() / total_volume)

        deviation_pct = ((close_now - vwap) / vwap * 100.0) if vwap else 0.0

        if deviation_pct <= -threshold_pct:
            direction = SignalDirection.BUY
            confidence = 0.5 + 0.5 * min(1.0, abs(deviation_pct) / (threshold_pct * 4))
            reason = f"Price ${close_now:.2f} is {abs(deviation_pct):.2f}% below VWAP ${vwap:.2f} — BUY (reversion up)."
        elif deviation_pct >= threshold_pct:
            direction = SignalDirection.SELL
            confidence = 0.5 + 0.5 * min(1.0, abs(deviation_pct) / (threshold_pct * 4))
            reason = f"Price ${close_now:.2f} is {deviation_pct:.2f}% above VWAP ${vwap:.2f} — SELL (reversion down)."
        else:
            direction = SignalDirection.HOLD
            confidence = 0.3 + 0.3 * (1.0 - abs(deviation_pct) / threshold_pct)
            reason = f"Price ${close_now:.2f} is within {threshold_pct:.2f}% of VWAP ${vwap:.2f} — holding."

        return self._create_signal(
            direction=direction,
            confidence=self._clamp_confidence(confidence),
            reason=reason,
            features=features,
        )
