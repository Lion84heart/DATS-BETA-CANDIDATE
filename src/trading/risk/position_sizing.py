"""Position sizing algorithms for risk-managed trading.

Implements Kelly Criterion, fixed fractional, and volatility-based
position sizing with configurable constraints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol



@dataclass(frozen=True)
class SizingResult:
    """Result of a position sizing calculation."""

    recommended_size: float
    max_size: float
    risk_fraction: float
    confidence: float
    method: str


class PositionSizingMethod(Protocol):
    """Protocol for position sizing methods."""

    def calculate(
        self,
        capital: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        current_price: float,
        volatility: float | None = None,
    ) -> SizingResult:
        ...


class KellyCriterion:
    """Kelly Criterion position sizing.

    f* = (p * b - q) / b
    where p = win probability, q = loss probability (1-p),
    b = avg_win / avg_loss (win/loss ratio).

    Uses fractional Kelly (default half-Kelly) for safety.
    """

    def __init__(self, fraction: float = 0.5, max_risk_per_trade: float = 0.02):
        """Initialize Kelly Criterion sizer.

        Args:
            fraction: Kelly fraction to use (0.5 = half-Kelly).
            max_risk_per_trade: Maximum capital risk per trade.
        """
        if not 0 < fraction <= 1.0:
            raise ValueError("fraction must be in (0, 1]")
        if not 0 < max_risk_per_trade <= 1.0:
            raise ValueError("max_risk_per_trade must be in (0, 1]")
        self.fraction = fraction
        self.max_risk_per_trade = max_risk_per_trade

    def calculate(
        self,
        capital: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        current_price: float,
        volatility: float | None = None,
    ) -> SizingResult:
        """Calculate position size using Kelly Criterion.

        Args:
            capital: Available capital.
            win_rate: Probability of winning (0-1).
            avg_win: Average winning trade amount.
            avg_loss: Average losing trade amount (positive value).
            current_price: Current market price.
            volatility: Optional volatility estimate.

        Returns:
            SizingResult with recommended position size.
        """
        if capital <= 0:
            raise ValueError("capital must be positive")
        if not 0 <= win_rate <= 1:
            raise ValueError("win_rate must be in [0, 1]")
        if avg_win <= 0 or avg_loss <= 0:
            raise ValueError("avg_win and avg_loss must be positive")
        if current_price <= 0:
            raise ValueError("current_price must be positive")

        q = 1.0 - win_rate
        b = avg_win / avg_loss  # win/loss ratio

        # Edge case: if b is 0, Kelly is undefined
        if b == 0:
            return SizingResult(
                recommended_size=0.0,
                max_size=0.0,
                risk_fraction=0.0,
                confidence=0.0,
                method="kelly",
            )

        # Kelly fraction
        kelly_f = (win_rate * b - q) / b
        kelly_f = max(0.0, min(kelly_f, 1.0))  # clamp to [0, 1]

        # Apply fractional Kelly
        adjusted_f = kelly_f * self.fraction

        # Cap at max risk per trade
        risk_fraction = min(adjusted_f, self.max_risk_per_trade)

        # Position size in currency
        position_value = capital * risk_fraction
        recommended_size = position_value / current_price

        # Max size is based on max_risk_per_trade alone
        max_position_value = capital * self.max_risk_per_trade
        max_size = max_position_value / current_price

        # Confidence based on edge strength
        edge = win_rate * b - q
        confidence = min(1.0, max(0.0, edge))

        return SizingResult(
            recommended_size=recommended_size,
            max_size=max_size,
            risk_fraction=risk_fraction,
            confidence=confidence,
            method="kelly",
        )

    def optimal_fraction(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """Return the raw optimal Kelly fraction (before applying safety fraction)."""
        q = 1.0 - win_rate
        b = avg_win / avg_loss
        if b == 0:
            return 0.0
        f = (win_rate * b - q) / b
        return max(0.0, min(f, 1.0))


class VolatilitySizer:
    """Volatility-based position sizing.

    Sizes positions inversely proportional to volatility.
    Higher volatility = smaller position size.
    """

    def __init__(
        self,
        target_volatility: float = 0.15,
        max_risk_per_trade: float = 0.02,
    ):
        """Initialize volatility-based sizer.

        Args:
            target_volatility: Annualized target volatility (e.g., 0.15 = 15%).
            max_risk_per_trade: Maximum capital risk per trade.
        """
        if target_volatility <= 0:
            raise ValueError("target_volatility must be positive")
        self.target_volatility = target_volatility
        self.max_risk_per_trade = max_risk_per_trade

    def calculate(
        self,
        capital: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        current_price: float,
        volatility: float | None = None,
    ) -> SizingResult:
        """Calculate position size based on volatility.

        Args:
            capital: Available capital.
            win_rate: Not used directly but kept for protocol compatibility.
            avg_win: Not used directly.
            avg_loss: Not used directly.
            current_price: Current market price.
            volatility: Annualized volatility estimate (required).

        Returns:
            SizingResult with recommended position size.
        """
        if capital <= 0:
            raise ValueError("capital must be positive")
        if current_price <= 0:
            raise ValueError("current_price must be positive")
        if volatility is None or volatility <= 0:
            raise ValueError("volatility must be provided and positive")

        # Scale position inversely by volatility relative to target
        vol_ratio = self.target_volatility / volatility
        vol_ratio = min(vol_ratio, 2.0)  # cap at 2x leverage

        # Risk fraction is vol-adjusted, capped at max_risk_per_trade
        risk_fraction = min(vol_ratio * self.max_risk_per_trade, self.max_risk_per_trade)

        position_value = capital * risk_fraction
        recommended_size = position_value / current_price
        max_size = (capital * self.max_risk_per_trade) / current_price

        return SizingResult(
            recommended_size=recommended_size,
            max_size=max_size,
            risk_fraction=risk_fraction,
            confidence=1.0,
            method="volatility",
        )


class PositionSizer:
    """Composite position sizer that can use multiple methods."""

    def __init__(self, method: str = "kelly", **kwargs):
        """Initialize composite sizer.

        Args:
            method: "kelly" or "volatility".
            **kwargs: Passed to the underlying sizer.
        """
        if method == "kelly":
            self._sizer: PositionSizingMethod = KellyCriterion(**kwargs)
        elif method == "volatility":
            self._sizer = VolatilitySizer(**kwargs)
        else:
            raise ValueError(f"Unknown sizing method: {method}")
        self.method = method

    def calculate(
        self,
        capital: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        current_price: float,
        volatility: float | None = None,
    ) -> SizingResult:
        """Calculate position size using the configured method."""
        return self._sizer.calculate(
            capital=capital,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            current_price=current_price,
            volatility=volatility,
        )
