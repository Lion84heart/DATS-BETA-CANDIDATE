"""Position Sizing Engine (Phase 4, module 6).

Replaces the baseline's fixed ``cash * position_size_pct`` sizing rule
with a volatility- and quality-scaled size: less capital committed
when ATR is elevated relative to its own trailing average, or when the
Trade Quality Score is only marginally favorable — more when both are
favorable. Bounded so this can never commit *more* capital to a single
position than the baseline itself would — only the same amount or less.
"""

from __future__ import annotations

import math

_MIN_FRACTION = 0.20  # never below 20% of the baseline's own max allocation
_MAX_FRACTION = 1.00  # never above the baseline's own max allocation


class PositionSizingEngine:
    def __init__(self, base_position_pct: float = 0.95) -> None:
        self.base_position_pct = base_position_pct

    def compute_size_fraction(self, quality_score: float, atr_ratio: float | None) -> float:
        """Fraction of ``base_position_pct`` to actually commit — 1.0 =
        full baseline size, 0.5 = half the baseline size."""
        quality_component = min(1.0, max(0.0, quality_score / 100.0))
        if atr_ratio is None or atr_ratio <= 0:
            volatility_component = 1.0
        else:
            # Elevated volatility (ratio > 1) scales size down; below-normal
            # volatility (ratio < 1) doesn't scale size up past the baseline.
            volatility_component = min(1.0, 1.0 / atr_ratio)
        fraction = quality_component * volatility_component
        return max(_MIN_FRACTION, min(_MAX_FRACTION, fraction))

    def compute_quantity(
        self, cash: float, price: float, quality_score: float, atr_ratio: float | None,
    ) -> int:
        if price <= 0:
            return 0
        fraction = self.compute_size_fraction(quality_score, atr_ratio)
        return math.floor((cash * self.base_position_pct * fraction) / price)
