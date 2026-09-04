"""DATS — Support / Resistance Strategy.

Identifies recent support (lowest low) and resistance (highest high)
over a rolling window. BUY when price is near support (potential
bounce), SELL when near resistance (potential rejection), HOLD in the
middle of the range. No LLM/external AI — a deterministic formula over
real OHLC data.

Note: with the engine's current tick-derived bars (high=low=close per
bar — a single tick carries no intrabar range), support/resistance here
reduces to the rolling min/max of close. The formula reads from the
high/low columns as given, so it will automatically use real intrabar
extremes if the engine is ever fed true OHLC bars.
"""

from __future__ import annotations

import pandas as pd

from trading.base_strategy import BaseStrategy
from trading.schemas import SignalDirection, StrategySignal, StrategyType

_DEFAULT_WINDOW = 30
_DEFAULT_PROXIMITY_PCT = 0.5  # % distance from support/resistance considered "near"


class SupportResistanceStrategy(BaseStrategy):
    """Rolling support/resistance proximity signal. Always returns a signal."""

    name = "support_resistance"
    strategy_type = StrategyType.MEAN_REVERSION

    def _apply_defaults(self) -> None:
        defaults = {"window": float(_DEFAULT_WINDOW), "proximity_pct": _DEFAULT_PROXIMITY_PCT}
        for key, value in defaults.items():
            if key not in self.parameters:
                self.parameters[key] = value
        self.config.parameters = dict(self.parameters)

    def parameter_bounds(self) -> dict[str, tuple[float, float]]:
        return {"window": (10.0, 100.0), "proximity_pct": (0.1, 3.0)}

    def generate_signal(
        self,
        ohlcv_df: pd.DataFrame,
        features: dict[str, float | None],
    ) -> StrategySignal:
        window = int(self.parameters.get("window", _DEFAULT_WINDOW))
        proximity_pct = self.parameters.get("proximity_pct", _DEFAULT_PROXIMITY_PCT)

        if ohlcv_df.empty or len(ohlcv_df) < min(window, 10):
            return self._create_signal(
                direction=SignalDirection.HOLD,
                confidence=0.1,
                reason=f"Support/Resistance: only {len(ohlcv_df)} bars available — insufficient history.",
                features=features,
            )

        recent = ohlcv_df.tail(window)
        support = float(recent["low"].min())
        resistance = float(recent["high"].max())
        close_now = float(recent["close"].iloc[-1])

        if resistance <= support:
            return self._create_signal(
                direction=SignalDirection.HOLD,
                confidence=0.2,
                reason="Support/Resistance: no meaningful range over the window — holding.",
                features=features,
            )

        range_size = resistance - support
        dist_to_support_pct = (close_now - support) / support * 100.0 if support else 0.0
        dist_to_resistance_pct = (resistance - close_now) / resistance * 100.0 if resistance else 0.0
        position_in_range = (close_now - support) / range_size  # 0 = at support, 1 = at resistance

        if dist_to_support_pct <= proximity_pct:
            direction = SignalDirection.BUY
            confidence = 0.5 + 0.5 * (1.0 - min(1.0, dist_to_support_pct / proximity_pct))
            reason = f"Price ${close_now:.2f} is within {proximity_pct:.2f}% of support ${support:.2f} — BUY (bounce)."
        elif dist_to_resistance_pct <= proximity_pct:
            direction = SignalDirection.SELL
            confidence = 0.5 + 0.5 * (1.0 - min(1.0, dist_to_resistance_pct / proximity_pct))
            reason = f"Price ${close_now:.2f} is within {proximity_pct:.2f}% of resistance ${resistance:.2f} — SELL (rejection)."
        else:
            direction = SignalDirection.HOLD
            confidence = 0.2 + 0.3 * (1.0 - abs(position_in_range - 0.5) * 2)
            reason = (
                f"Price ${close_now:.2f} is mid-range between support ${support:.2f} and "
                f"resistance ${resistance:.2f} — holding."
            )

        return self._create_signal(
            direction=direction,
            confidence=self._clamp_confidence(confidence),
            reason=reason,
            features=features,
        )
