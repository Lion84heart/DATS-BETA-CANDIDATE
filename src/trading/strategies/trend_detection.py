"""DATS — Trend Detection Strategy.

Fits a linear regression to the last N closes. A significantly positive
slope (relative to price) with a good fit (high R^2) is a BUY; a
significantly negative slope with a good fit is a SELL; a flat or noisy
fit is a HOLD. Distinct from EMA Cross (which reacts to crossover
events): this measures the strength and consistency of the underlying
trend itself. No LLM/external AI — a deterministic least-squares fit
over real close-price history.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading.base_strategy import BaseStrategy
from trading.schemas import SignalDirection, StrategySignal, StrategyType

_DEFAULT_WINDOW = 20
_DEFAULT_SLOPE_THRESHOLD_PCT = 0.05  # % price change per bar considered a real trend
_DEFAULT_MIN_R2 = 0.3


class TrendDetectionStrategy(BaseStrategy):
    """Linear-regression trend-strength signal. Always returns a signal."""

    name = "trend_detection"
    strategy_type = StrategyType.TREND_FOLLOWING

    def _apply_defaults(self) -> None:
        defaults = {
            "window": float(_DEFAULT_WINDOW),
            "slope_threshold_pct": _DEFAULT_SLOPE_THRESHOLD_PCT,
            "min_r2": _DEFAULT_MIN_R2,
        }
        for key, value in defaults.items():
            if key not in self.parameters:
                self.parameters[key] = value
        self.config.parameters = dict(self.parameters)

    def parameter_bounds(self) -> dict[str, tuple[float, float]]:
        return {"window": (10.0, 100.0), "slope_threshold_pct": (0.01, 1.0), "min_r2": (0.0, 0.9)}

    def generate_signal(
        self,
        ohlcv_df: pd.DataFrame,
        features: dict[str, float | None],
    ) -> StrategySignal:
        window = int(self.parameters.get("window", _DEFAULT_WINDOW))
        slope_threshold_pct = self.parameters.get("slope_threshold_pct", _DEFAULT_SLOPE_THRESHOLD_PCT)
        min_r2 = self.parameters.get("min_r2", _DEFAULT_MIN_R2)

        if ohlcv_df.empty or len(ohlcv_df) < window:
            return self._create_signal(
                direction=SignalDirection.HOLD,
                confidence=0.1,
                reason=f"Trend Detection: only {len(ohlcv_df)}/{window} bars available — insufficient history.",
                features=features,
            )

        closes = ohlcv_df["close"].tail(window).to_numpy(dtype=float)
        x = np.arange(len(closes), dtype=float)
        mean_price = float(closes.mean())

        if mean_price == 0:
            return self._create_signal(
                direction=SignalDirection.HOLD,
                confidence=0.2,
                reason="Trend Detection: zero mean price over the window — holding.",
                features=features,
            )

        slope, intercept = np.polyfit(x, closes, 1)
        fitted = slope * x + intercept
        ss_res = float(np.sum((closes - fitted) ** 2))
        ss_tot = float(np.sum((closes - mean_price) ** 2))
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        slope_pct_per_bar = (slope / mean_price) * 100.0

        strong_fit = r2 >= min_r2

        if slope_pct_per_bar >= slope_threshold_pct and strong_fit:
            direction = SignalDirection.BUY
            confidence = 0.4 + 0.3 * min(1.0, r2) + 0.3 * min(1.0, slope_pct_per_bar / (slope_threshold_pct * 4))
            reason = (
                f"Upward trend: {slope_pct_per_bar:.3f}%/bar slope, R^2={r2:.2f} over {window} bars — BUY."
            )
        elif slope_pct_per_bar <= -slope_threshold_pct and strong_fit:
            direction = SignalDirection.SELL
            confidence = 0.4 + 0.3 * min(1.0, r2) + 0.3 * min(1.0, abs(slope_pct_per_bar) / (slope_threshold_pct * 4))
            reason = (
                f"Downward trend: {slope_pct_per_bar:.3f}%/bar slope, R^2={r2:.2f} over {window} bars — SELL."
            )
        else:
            direction = SignalDirection.HOLD
            confidence = 0.2 + 0.2 * (1.0 - min(1.0, abs(slope_pct_per_bar) / slope_threshold_pct))
            reason = (
                f"No consistent trend: {slope_pct_per_bar:.3f}%/bar slope, R^2={r2:.2f} "
                f"(below threshold or too noisy) — holding."
            )

        return self._create_signal(
            direction=direction,
            confidence=self._clamp_confidence(confidence),
            reason=reason,
            features=features,
        )
