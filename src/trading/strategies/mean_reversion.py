"""DATS — Mean Reversion Strategy.

Mean reversion using Bollinger Bands + RSI.
BUY when price hits lower band and RSI < oversold threshold.
SELL when price hits upper band and RSI > overbought threshold.
Confidence based on distance from mean + RSI extremity.
"""

from __future__ import annotations

import logging
import math

import pandas as pd

from trading.base_strategy import BaseStrategy
from trading.schemas import SignalDirection, StrategySignal, StrategyType

logger = logging.getLogger(__name__)


class MeanReversionStrategy(BaseStrategy):
    """Mean reversion strategy using Bollinger Bands + RSI.

    Parameters:
        bb_period: Bollinger Bands lookback period (default: 20)
        bb_std: Standard deviation multiplier (default: 2.0)
        rsi_period: RSI period (default: 14)
        rsi_oversold: RSI oversold threshold (default: 30)
        rsi_overbought: RSI overbought threshold (default: 70)
    """

    name = "mean_reversion"
    strategy_type = StrategyType.MEAN_REVERSION

    _DEFAULT_BB_PERIOD: float = 20.0
    _DEFAULT_BB_STD: float = 2.0
    _DEFAULT_RSI_PERIOD: float = 14.0
    _DEFAULT_RSI_OVERSOLD: float = 30.0
    _DEFAULT_RSI_OVERBOUGHT: float = 70.0

    def _apply_defaults(self) -> None:
        defaults = {
            "bb_period": self._DEFAULT_BB_PERIOD,
            "bb_std": self._DEFAULT_BB_STD,
            "rsi_period": self._DEFAULT_RSI_PERIOD,
            "rsi_oversold": self._DEFAULT_RSI_OVERSOLD,
            "rsi_overbought": self._DEFAULT_RSI_OVERBOUGHT,
        }
        for key, value in defaults.items():
            if key not in self.parameters:
                self.parameters[key] = value
        self.config.parameters = dict(self.parameters)

    def parameter_bounds(self) -> dict[str, tuple[float, float]]:
        return {
            "bb_period": (5.0, 50.0),
            "bb_std": (0.5, 4.0),
            "rsi_period": (5.0, 30.0),
            "rsi_oversold": (10.0, 40.0),
            "rsi_overbought": (60.0, 90.0),
        }

    def generate_signal(
        self,
        ohlcv_df: pd.DataFrame,
        features: dict[str, float | None],
    ) -> StrategySignal | None:
        """Generate mean-reversion signal from Bollinger Bands + RSI."""
        rsi_oversold = self.parameters.get("rsi_oversold", self._DEFAULT_RSI_OVERSOLD)
        rsi_overbought = self.parameters.get("rsi_overbought", self._DEFAULT_RSI_OVERBOUGHT)

        # Extract features
        bb_lower = self._safe_feature(features, "bb_lower")
        bb_upper = self._safe_feature(features, "bb_upper")
        rsi_val = self._safe_feature(features, "rsi_14")
        close = self._safe_feature(features, "close")

        # Fallback: compute from OHLCV if features not available
        if bb_lower is None or bb_upper is None:
            if ohlcv_df.empty or len(ohlcv_df) < 25:
                return None
            close_series = ohlcv_df["close"]
            sma = close_series.rolling(window=20).mean()
            std = close_series.rolling(window=20).std()
            bb_lower = float((sma - 2.0 * std).iloc[-1])
            bb_upper = float((sma + 2.0 * std).iloc[-1])

        if rsi_val is None:
            if ohlcv_df.empty or len(ohlcv_df) < 20:
                return None
            # Compute RSI manually
            close_series = ohlcv_df["close"]
            rsi_val = self._compute_rsi(close_series, 14)

        if close is None:
            if not ohlcv_df.empty:
                close = float(ohlcv_df["close"].iloc[-1])

        if close is None or math.isnan(close):
            return None
        if bb_lower is None or bb_upper is None or math.isnan(bb_lower) or math.isnan(bb_upper):
            return None
        if rsi_val is None or math.isnan(rsi_val):
            return None

        # Compute mid-band for distance calculation
        bb_mid = (bb_upper + bb_lower) / 2.0
        band_width = bb_upper - bb_lower

        # BUY: price near lower band and RSI oversold
        if close <= bb_lower and rsi_val <= rsi_oversold:
            rsi_extremity = max(0.0, (rsi_oversold - rsi_val) / rsi_oversold) if rsi_oversold > 0 else 0
            dist_from_mean = 0.0
            if band_width > 0:
                dist_from_mean = abs(close - bb_mid) / (band_width / 2.0)
            confidence = 0.4 + 0.35 * rsi_extremity + 0.25 * min(1.0, dist_from_mean)
            reason = (
                f"BUY: Price {close:.4f} at/below lower BB {bb_lower:.4f} "
                f"with RSI={rsi_val:.1f} (oversold, threshold={rsi_oversold})"
            )
            direction = SignalDirection.BUY

        # SELL: price near upper band and RSI overbought
        elif close >= bb_upper and rsi_val >= rsi_overbought:
            rsi_extremity = max(0.0, (rsi_val - rsi_overbought) / (100.0 - rsi_overbought)) if rsi_overbought < 100 else 0
            dist_from_mean = 0.0
            if band_width > 0:
                dist_from_mean = abs(close - bb_mid) / (band_width / 2.0)
            confidence = 0.4 + 0.35 * rsi_extremity + 0.25 * min(1.0, dist_from_mean)
            reason = (
                f"SELL: Price {close:.4f} at/above upper BB {bb_upper:.4f} "
                f"with RSI={rsi_val:.1f} (overbought, threshold={rsi_overbought})"
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
    def _compute_rsi(series: pd.Series, period: int) -> float | None:
        """Compute RSI for a price series."""
        if len(series) < period + 1:
            return None
        delta = series.diff().dropna()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean().iloc[-1]
        avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean().iloc[-1]
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
