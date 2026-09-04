"""DATS — Volume Profile Strategy.

Buckets recent closes into price bins weighted by traded volume to find
the Point of Control (POC) — the price level with the most volume. BUY
when price is meaningfully below POC (volume suggests it's the fairer
value, pulling price up), SELL when meaningfully above, HOLD near POC.
No LLM/external AI — a deterministic computation over real price/volume
data.

This is a simplified volume profile: it bins closing prices (not true
intrabar traded price levels, which the engine's tick-derived bars
don't carry), a standard and honest approximation when only per-bar
close+volume is available.
"""

from __future__ import annotations

import pandas as pd

from trading.base_strategy import BaseStrategy
from trading.schemas import SignalDirection, StrategySignal, StrategyType

_DEFAULT_WINDOW = 40
_DEFAULT_BINS = 12
_DEFAULT_THRESHOLD_PCT = 0.5


class VolumeProfileStrategy(BaseStrategy):
    """Point-of-Control deviation signal. Always returns a signal."""

    name = "volume_profile"
    strategy_type = StrategyType.STATISTICAL_ARBITRAGE

    def _apply_defaults(self) -> None:
        defaults = {
            "window": float(_DEFAULT_WINDOW),
            "bins": float(_DEFAULT_BINS),
            "threshold_pct": _DEFAULT_THRESHOLD_PCT,
        }
        for key, value in defaults.items():
            if key not in self.parameters:
                self.parameters[key] = value
        self.config.parameters = dict(self.parameters)

    def parameter_bounds(self) -> dict[str, tuple[float, float]]:
        return {"window": (15.0, 100.0), "bins": (5.0, 30.0), "threshold_pct": (0.1, 3.0)}

    def generate_signal(
        self,
        ohlcv_df: pd.DataFrame,
        features: dict[str, float | None],
    ) -> StrategySignal:
        window = int(self.parameters.get("window", _DEFAULT_WINDOW))
        num_bins = int(self.parameters.get("bins", _DEFAULT_BINS))
        threshold_pct = self.parameters.get("threshold_pct", _DEFAULT_THRESHOLD_PCT)
        min_bars = max(num_bins, 15)

        if ohlcv_df.empty or len(ohlcv_df) < min_bars:
            return self._create_signal(
                direction=SignalDirection.HOLD,
                confidence=0.1,
                reason=f"Volume Profile: only {len(ohlcv_df)}/{min_bars} bars available — insufficient history.",
                features=features,
            )

        recent = ohlcv_df.tail(window).copy()
        close_now = float(recent["close"].iloc[-1])
        price_min, price_max = float(recent["close"].min()), float(recent["close"].max())

        if price_max <= price_min:
            return self._create_signal(
                direction=SignalDirection.HOLD,
                confidence=0.2,
                reason="Volume Profile: no price range over the window — holding.",
                features=features,
            )

        try:
            recent["bin"] = pd.cut(recent["close"], bins=num_bins, include_lowest=True)
            volume_by_bin = recent.groupby("bin", observed=True)["volume"].sum()
            poc_bin = volume_by_bin.idxmax()
            poc_price = float(poc_bin.mid)
        except Exception:
            return self._create_signal(
                direction=SignalDirection.HOLD,
                confidence=0.2,
                reason="Volume Profile: could not compute a point of control — holding.",
                features=features,
            )

        deviation_pct = (close_now - poc_price) / poc_price * 100.0 if poc_price else 0.0

        if deviation_pct <= -threshold_pct:
            direction = SignalDirection.BUY
            confidence = 0.5 + 0.5 * min(1.0, abs(deviation_pct) / (threshold_pct * 4))
            reason = f"Price ${close_now:.2f} is {abs(deviation_pct):.2f}% below the volume point of control ${poc_price:.2f} — BUY."
        elif deviation_pct >= threshold_pct:
            direction = SignalDirection.SELL
            confidence = 0.5 + 0.5 * min(1.0, abs(deviation_pct) / (threshold_pct * 4))
            reason = f"Price ${close_now:.2f} is {deviation_pct:.2f}% above the volume point of control ${poc_price:.2f} — SELL."
        else:
            direction = SignalDirection.HOLD
            confidence = 0.3 + 0.3 * (1.0 - abs(deviation_pct) / threshold_pct)
            reason = f"Price ${close_now:.2f} is close to the volume point of control ${poc_price:.2f} — holding."

        return self._create_signal(
            direction=direction,
            confidence=self._clamp_confidence(confidence),
            reason=reason,
            features=features,
        )
