"""DATS — Breakout Strategy.

Breakout trading using ATR-based channels + volume confirmation.
BUY on upper channel breakout with high volume.
SELL on lower channel breakout with high volume.
Confidence based on breakout strength + volume ratio.
"""

from __future__ import annotations

import logging
import math

import pandas as pd

from trading.base_strategy import BaseStrategy
from trading.schemas import SignalDirection, StrategySignal, StrategyType

logger = logging.getLogger(__name__)


class BreakoutStrategy(BaseStrategy):
    """Breakout strategy using ATR-based channels + volume confirmation.

    Parameters:
        lookback: Lookback period for channel calculation (default: 20)
        atr_multiplier: ATR multiplier for channel width (default: 1.5)
        volume_threshold: Volume multiplier threshold (default: 2.0)
    """

    name = "breakout"
    strategy_type = StrategyType.BREAKOUT

    _DEFAULT_LOOKBACK: float = 20.0
    _DEFAULT_ATR_MULTIPLIER: float = 1.5
    _DEFAULT_VOLUME_THRESHOLD: float = 2.0

    def _apply_defaults(self) -> None:
        defaults = {
            "lookback": self._DEFAULT_LOOKBACK,
            "atr_multiplier": self._DEFAULT_ATR_MULTIPLIER,
            "volume_threshold": self._DEFAULT_VOLUME_THRESHOLD,
        }
        for key, value in defaults.items():
            if key not in self.parameters:
                self.parameters[key] = value
        self.config.parameters = dict(self.parameters)

    def parameter_bounds(self) -> dict[str, tuple[float, float]]:
        return {
            "lookback": (5.0, 100.0),
            "atr_multiplier": (0.5, 5.0),
            "volume_threshold": (1.0, 10.0),
        }

    def generate_signal(
        self,
        ohlcv_df: pd.DataFrame,
        features: dict[str, float | None],
    ) -> StrategySignal | None:
        """Generate breakout signal from ATR-based channels + volume."""
        lookback = int(self.parameters.get("lookback", self._DEFAULT_LOOKBACK))
        atr_multiplier = self.parameters.get(
            "atr_multiplier", self._DEFAULT_ATR_MULTIPLIER
        )
        volume_threshold = self.parameters.get(
            "volume_threshold", self._DEFAULT_VOLUME_THRESHOLD
        )

        if ohlcv_df.empty or len(ohlcv_df) < lookback + 5:
            return None

        high_series = ohlcv_df["high"]
        low_series = ohlcv_df["low"]
        close_series = ohlcv_df["close"]
        volume_series = ohlcv_df["volume"]

        current_close = float(close_series.iloc[-1])
        prev_close = float(close_series.iloc[-2])

        # Compute ATR-based channels
        atr_val = self._compute_atr(ohlcv_df, 14)
        if atr_val is None or math.isnan(atr_val):
            return None

        # Channel based on recent highs/lows +/- ATR
        recent_high = float(high_series.iloc[-lookback:].max())
        recent_low = float(low_series.iloc[-lookback:].min())

        upper_channel = recent_high + atr_multiplier * atr_val
        lower_channel = recent_low - atr_multiplier * atr_val

        # Volume check
        current_volume = float(volume_series.iloc[-1])
        avg_volume = float(volume_series.iloc[-lookback:].mean())
        vol_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

        if vol_ratio < volume_threshold:
            return None

        # BUY: upper channel breakout
        if current_close > upper_channel and prev_close <= upper_channel:
            breakout_strength = (current_close - upper_channel) / atr_val if atr_val > 0 else 0
            vol_confidence = min(1.0, (vol_ratio - volume_threshold) / volume_threshold) if volume_threshold > 0 else 0
            confidence = 0.4 + 0.35 * min(1.0, breakout_strength) + 0.25 * vol_confidence
            reason = (
                f"BUY: Upper channel breakout at {current_close:.4f} "
                f"(channel={upper_channel:.4f}, ATR={atr_val:.4f}) "
                f"with volume {vol_ratio:.2f}x"
            )
            direction = SignalDirection.BUY

        # SELL: lower channel breakout
        elif current_close < lower_channel and prev_close >= lower_channel:
            breakout_strength = (lower_channel - current_close) / atr_val if atr_val > 0 else 0
            vol_confidence = min(1.0, (vol_ratio - volume_threshold) / volume_threshold) if volume_threshold > 0 else 0
            confidence = 0.4 + 0.35 * min(1.0, breakout_strength) + 0.25 * vol_confidence
            reason = (
                f"SELL: Lower channel breakout at {current_close:.4f} "
                f"(channel={lower_channel:.4f}, ATR={atr_val:.4f}) "
                f"with volume {vol_ratio:.2f}x"
            )
            direction = SignalDirection.SELL
        else:
            return None

        confidence = self._clamp_confidence(confidence)

        return self._create_signal(
            direction=direction,
            confidence=confidence,
            reason=reason,
            features=features,
        )

    @staticmethod
    def _compute_atr(df: pd.DataFrame, period: int) -> float | None:
        """Compute Average True Range."""
        if len(df) < period + 1:
            return None
        high = df["high"]
        low = df["low"]
        close = df["close"]
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        val = atr.iloc[-1]
        if math.isnan(val):
            return None
        return float(val)
