"""DATS — Statistical Arbitrage Strategy.

Statistical arbitrage using z-score mean reversion.
BUY when z-score < -entry_threshold (price below mean).
SELL when z-score > entry_threshold (price above mean).
Confidence based on z-score magnitude.
"""

from __future__ import annotations

import logging
import math

import pandas as pd

from trading.base_strategy import BaseStrategy
from trading.schemas import SignalDirection, StrategySignal, StrategyType

logger = logging.getLogger(__name__)


class StatArbStrategy(BaseStrategy):
    """Statistical arbitrage strategy using z-score mean reversion.

    Parameters:
        zscore_window: Rolling window for z-score calculation (default: 20)
        entry_threshold: Z-score threshold for entry (default: 2.0)
        exit_threshold: Z-score threshold for exit (default: 0.5)
    """

    name = "stat_arb"
    strategy_type = StrategyType.STATISTICAL_ARBITRAGE

    _DEFAULT_ZSCORE_WINDOW: float = 20.0
    _DEFAULT_ENTRY_THRESHOLD: float = 2.0
    _DEFAULT_EXIT_THRESHOLD: float = 0.5

    def _apply_defaults(self) -> None:
        defaults = {
            "zscore_window": self._DEFAULT_ZSCORE_WINDOW,
            "entry_threshold": self._DEFAULT_ENTRY_THRESHOLD,
            "exit_threshold": self._DEFAULT_EXIT_THRESHOLD,
        }
        for key, value in defaults.items():
            if key not in self.parameters:
                self.parameters[key] = value
        self.config.parameters = dict(self.parameters)

    def parameter_bounds(self) -> dict[str, tuple[float, float]]:
        return {
            "zscore_window": (5.0, 100.0),
            "entry_threshold": (0.5, 5.0),
            "exit_threshold": (0.0, 2.0),
        }

    def generate_signal(
        self,
        ohlcv_df: pd.DataFrame,
        features: dict[str, float | None],
    ) -> StrategySignal | None:
        """Generate statistical arbitrage signal from z-score mean reversion."""
        zscore_window = int(
            self.parameters.get("zscore_window", self._DEFAULT_ZSCORE_WINDOW)
        )
        entry_threshold = self.parameters.get(
            "entry_threshold", self._DEFAULT_ENTRY_THRESHOLD
        )
        exit_threshold = self.parameters.get(
            "exit_threshold", self._DEFAULT_EXIT_THRESHOLD
        )

        # Extract z-score from features
        zscore = self._safe_feature(features, "z_score")

        # Fallback: compute from OHLCV
        if zscore is None:
            if ohlcv_df.empty or len(ohlcv_df) < zscore_window + 1:
                return None
            close_series = ohlcv_df["close"]
            window = close_series.iloc[-zscore_window:]
            mean = window.mean()
            std = window.std()
            if std == 0 or math.isnan(std):
                return None
            zscore = float((close_series.iloc[-1] - mean) / std)

        if zscore is None or math.isnan(zscore):
            return None

        # Track previous z-score from state for exit signals
        prev_zscore = self._state_data.get("prev_zscore")
        self._state_data["prev_zscore"] = zscore

        # BUY: z-score below negative entry threshold (price is below mean)
        if zscore <= -entry_threshold:
            zscore_magnitude = min(1.0, abs(zscore) / (2.0 * entry_threshold)) if entry_threshold > 0 else 0.5
            confidence = 0.5 + 0.5 * zscore_magnitude
            reason = (
                f"BUY: Z-score={zscore:.3f} below -{entry_threshold} "
                f"(price significantly below mean, mean-reversion expected)"
            )
            direction = SignalDirection.BUY

        # SELL: z-score above entry threshold (price is above mean)
        elif zscore >= entry_threshold:
            zscore_magnitude = min(1.0, abs(zscore) / (2.0 * entry_threshold)) if entry_threshold > 0 else 0.5
            confidence = 0.5 + 0.5 * zscore_magnitude
            reason = (
                f"SELL: Z-score={zscore:.3f} above +{entry_threshold} "
                f"(price significantly above mean, mean-reversion expected)"
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
