"""DATS — Trend Following Strategy.

Follows trends using EMA crossover with ADX confirmation.
BUY when fast EMA > slow EMA and ADX > threshold.
SELL when fast EMA < slow EMA and ADX > threshold.
Confidence proportional to ADX strength + EMA separation.
"""

from __future__ import annotations

import logging
import math

import pandas as pd

from trading.base_strategy import BaseStrategy
from trading.schemas import SignalDirection, StrategySignal, StrategyType

logger = logging.getLogger(__name__)


class TrendFollowingStrategy(BaseStrategy):
    """Trend following strategy using EMA crossover + ADX confirmation.

    Parameters:
        fast_ema: Fast EMA period (default: 9)
        slow_ema: Slow EMA period (default: 21)
        adx_threshold: Minimum ADX for trend confirmation (default: 25)
    """

    name = "trend_following"
    strategy_type = StrategyType.TREND_FOLLOWING

    # Default parameters
    _DEFAULT_FAST_EMA: float = 9.0
    _DEFAULT_SLOW_EMA: float = 21.0
    _DEFAULT_ADX_THRESHOLD: float = 25.0

    def _apply_defaults(self) -> None:
        defaults = {
            "fast_ema": self._DEFAULT_FAST_EMA,
            "slow_ema": self._DEFAULT_SLOW_EMA,
            "adx_threshold": self._DEFAULT_ADX_THRESHOLD,
        }
        for key, value in defaults.items():
            if key not in self.parameters:
                self.parameters[key] = value
        self.config.parameters = dict(self.parameters)

    def parameter_bounds(self) -> dict[str, tuple[float, float]]:
        return {
            "fast_ema": (3.0, 50.0),
            "slow_ema": (10.0, 200.0),
            "adx_threshold": (10.0, 50.0),
        }

    def generate_signal(
        self,
        ohlcv_df: pd.DataFrame,
        features: dict[str, float | None],
    ) -> StrategySignal | None:
        """Generate trend-following signal from EMA crossover + ADX."""
        fast_ema = self.parameters.get("fast_ema", self._DEFAULT_FAST_EMA)
        slow_ema = self.parameters.get("slow_ema", self._DEFAULT_SLOW_EMA)
        adx_threshold = self.parameters.get("adx_threshold", self._DEFAULT_ADX_THRESHOLD)

        # Extract features (NaN-safe)
        ema_fast_val = self._safe_feature(features, f"ema_{int(fast_ema)}")
        ema_slow_val = self._safe_feature(features, f"ema_{int(slow_ema)}")
        adx_val = self._safe_feature(features, "adx_14")
        close = self._safe_feature(features, "close")

        # If we can't get the specific EMA periods from features, compute from OHLCV
        if ema_fast_val is None or ema_slow_val is None:
            if ohlcv_df.empty or len(ohlcv_df) < int(slow_ema) + 5:
                return None
            close_series = ohlcv_df["close"]
            ema_fast_series = close_series.ewm(span=int(fast_ema), adjust=False).mean()
            ema_slow_series = close_series.ewm(span=int(slow_ema), adjust=False).mean()
            ema_fast_val = float(ema_fast_series.iloc[-1])
            ema_slow_val = float(ema_slow_series.iloc[-1])

        if adx_val is None:
            return None

        if math.isnan(ema_fast_val) or math.isnan(ema_slow_val) or math.isnan(adx_val):
            return None

        # Determine direction
        if ema_fast_val > ema_slow_val and adx_val >= adx_threshold:
            direction = SignalDirection.BUY
            ema_separation = abs(ema_fast_val - ema_slow_val) / ema_slow_val if ema_slow_val > 0 else 0
            adx_strength = min(1.0, (adx_val - adx_threshold) / 50.0) if adx_val > adx_threshold else 0
            confidence = 0.5 + 0.3 * adx_strength + 0.2 * min(1.0, ema_separation * 100)
            reason = (
                f"BUY: EMA{int(fast_ema)} ({ema_fast_val:.4f}) > EMA{int(slow_ema)} "
                f"({ema_slow_val:.4f}) with ADX={adx_val:.1f} (trend confirmed)"
            )
        elif ema_fast_val < ema_slow_val and adx_val >= adx_threshold:
            direction = SignalDirection.SELL
            ema_separation = abs(ema_fast_val - ema_slow_val) / ema_slow_val if ema_slow_val > 0 else 0
            adx_strength = min(1.0, (adx_val - adx_threshold) / 50.0) if adx_val > adx_threshold else 0
            confidence = 0.5 + 0.3 * adx_strength + 0.2 * min(1.0, ema_separation * 100)
            reason = (
                f"SELL: EMA{int(fast_ema)} ({ema_fast_val:.4f}) < EMA{int(slow_ema)} "
                f"({ema_slow_val:.4f}) with ADX={adx_val:.1f} (trend confirmed)"
            )
        else:
            return None

        confidence = self._clamp_confidence(confidence)

        return self._create_signal(
            direction=direction,
            confidence=confidence,
            reason=reason,
            features=features,
        )
