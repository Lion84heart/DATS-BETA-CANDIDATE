"""DATS — Momentum Strategy.

Momentum using MACD crossover + volume confirmation.
BUY on MACD bullish crossover with volume > threshold * average.
SELL on MACD bearish crossover with volume > threshold * average.
Confidence based on histogram strength + volume ratio.
"""

from __future__ import annotations

import logging
import math

import pandas as pd

from trading.base_strategy import BaseStrategy
from trading.schemas import SignalDirection, StrategySignal, StrategyType

logger = logging.getLogger(__name__)


class MomentumStrategy(BaseStrategy):
    """Momentum strategy using MACD crossover + volume confirmation.

    Parameters:
        macd_fast: MACD fast period (default: 12)
        macd_slow: MACD slow period (default: 26)
        macd_signal: MACD signal period (default: 9)
        volume_threshold: Volume multiplier threshold (default: 1.5)
    """

    name = "momentum"
    strategy_type = StrategyType.MOMENTUM

    _DEFAULT_MACD_FAST: float = 12.0
    _DEFAULT_MACD_SLOW: float = 26.0
    _DEFAULT_MACD_SIGNAL: float = 9.0
    _DEFAULT_VOLUME_THRESHOLD: float = 1.5

    def _apply_defaults(self) -> None:
        defaults = {
            "macd_fast": self._DEFAULT_MACD_FAST,
            "macd_slow": self._DEFAULT_MACD_SLOW,
            "macd_signal": self._DEFAULT_MACD_SIGNAL,
            "volume_threshold": self._DEFAULT_VOLUME_THRESHOLD,
        }
        for key, value in defaults.items():
            if key not in self.parameters:
                self.parameters[key] = value
        self.config.parameters = dict(self.parameters)

    def parameter_bounds(self) -> dict[str, tuple[float, float]]:
        return {
            "macd_fast": (5.0, 20.0),
            "macd_slow": (15.0, 50.0),
            "macd_signal": (5.0, 20.0),
            "volume_threshold": (1.0, 5.0),
        }

    def generate_signal(
        self,
        ohlcv_df: pd.DataFrame,
        features: dict[str, float | None],
    ) -> StrategySignal | None:
        """Generate momentum signal from MACD crossover + volume."""
        volume_threshold = self.parameters.get(
            "volume_threshold", self._DEFAULT_VOLUME_THRESHOLD
        )

        # Extract features
        macd_hist = self._safe_feature(features, "macd_histogram")
        macd_val = self._safe_feature(features, "macd")
        macd_signal_val = self._safe_feature(features, "macd_signal")
        relative_volume = self._safe_feature(features, "relative_volume")
        volume_change = self._safe_feature(features, "volume_change")
        close = self._safe_feature(features, "close")

        # Need OHLCV for MACD computation and volume analysis
        if ohlcv_df.empty or len(ohlcv_df) < 35:
            return None

        close_series = ohlcv_df["close"]
        volume_series = ohlcv_df["volume"]

        # Compute or validate MACD
        if macd_val is None or macd_signal_val is None or macd_hist is None:
            macd_fast = int(self.parameters.get("macd_fast", self._DEFAULT_MACD_FAST))
            macd_slow = int(self.parameters.get("macd_slow", self._DEFAULT_MACD_SLOW))
            macd_signal_p = int(self.parameters.get("macd_signal", self._DEFAULT_MACD_SIGNAL))
            ema_fast = close_series.ewm(span=macd_fast, adjust=False).mean()
            ema_slow = close_series.ewm(span=macd_slow, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=macd_signal_p, adjust=False).mean()
            histogram = macd_line - signal_line
            macd_val = float(macd_line.iloc[-1])
            macd_signal_val = float(signal_line.iloc[-1])
            macd_hist = float(histogram.iloc[-1])
            # Previous values for crossover detection
            macd_hist_prev = float(histogram.iloc[-2])
        else:
            # Need previous histogram for crossover detection
            macd_fast = int(self.parameters.get("macd_fast", self._DEFAULT_MACD_FAST))
            macd_slow = int(self.parameters.get("macd_slow", self._DEFAULT_MACD_SLOW))
            macd_signal_p = int(self.parameters.get("macd_signal", self._DEFAULT_MACD_SIGNAL))
            ema_fast = close_series.ewm(span=macd_fast, adjust=False).mean()
            ema_slow = close_series.ewm(span=macd_slow, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=macd_signal_p, adjust=False).mean()
            histogram = macd_line - signal_line
            macd_hist_prev = float(histogram.iloc[-2])

        # Volume check
        current_volume = float(volume_series.iloc[-1])
        avg_volume = float(volume_series.iloc[-20:].mean()) if len(volume_series) >= 20 else current_volume
        vol_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

        if vol_ratio < volume_threshold:
            return None

        if math.isnan(macd_hist) or math.isnan(macd_hist_prev):
            return None

        # Bullish crossover: histogram turns positive
        if macd_hist > 0 and macd_hist_prev <= 0:
            hist_strength = min(1.0, abs(macd_hist) / (abs(close_series.iloc[-1]) * 0.01)) if close_series.iloc[-1] != 0 else 0.5
            vol_confidence = min(1.0, (vol_ratio - volume_threshold) / volume_threshold) if volume_threshold > 0 else 0
            confidence = 0.4 + 0.35 * min(1.0, hist_strength) + 0.25 * vol_confidence
            reason = (
                f"BUY: MACD histogram turned positive ({macd_hist:.6f}) "
                f"with volume ratio {vol_ratio:.2f}x (threshold={volume_threshold})"
            )
            direction = SignalDirection.BUY

        # Bearish crossover: histogram turns negative
        elif macd_hist < 0 and macd_hist_prev >= 0:
            hist_strength = min(1.0, abs(macd_hist) / (abs(close_series.iloc[-1]) * 0.01)) if close_series.iloc[-1] != 0 else 0.5
            vol_confidence = min(1.0, (vol_ratio - volume_threshold) / volume_threshold) if volume_threshold > 0 else 0
            confidence = 0.4 + 0.35 * min(1.0, hist_strength) + 0.25 * vol_confidence
            reason = (
                f"SELL: MACD histogram turned negative ({macd_hist:.6f}) "
                f"with volume ratio {vol_ratio:.2f}x (threshold={volume_threshold})"
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
