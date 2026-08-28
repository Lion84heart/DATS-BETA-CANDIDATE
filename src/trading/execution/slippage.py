"""Slippage models for execution price estimation.

Models the difference between expected fill price and actual fill price
due to market impact, liquidity, and volatility.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol



class SlippageModel(Protocol):
    """Protocol for slippage models."""

    def estimate_slippage(
        self,
        expected_price: float,
        quantity: float,
        side: str,
        volatility: float | None = None,
        volume: float | None = None,
    ) -> float:
        ...


@dataclass(frozen=True)
class FixedSlippage:
    """Fixed dollar or percentage slippage."""

    amount: float = 0.01
    is_percentage: bool = False

    def estimate_slippage(
        self,
        expected_price: float,
        quantity: float,
        side: str,
        volatility: float | None = None,
        volume: float | None = None,
    ) -> float:
        if self.is_percentage:
            return expected_price * self.amount
        return self.amount


@dataclass(frozen=True)
class VolatilitySlippage:
    """Slippage proportional to volatility and order size relative to volume."""

    base_bps: float = 5.0  # Base slippage in basis points
    vol_multiplier: float = 10.0  # Additional bps per unit of annualized vol
    size_multiplier: float = 50.0  # Additional bps when order = volume

    def estimate_slippage(
        self,
        expected_price: float,
        quantity: float,
        side: str,
        volatility: float | None = None,
        volume: float | None = None,
    ) -> float:
        bps = self.base_bps
        if volatility is not None:
            bps += volatility * self.vol_multiplier
        if volume is not None and volume > 0:
            bps += (quantity / volume) * self.size_multiplier
        # Convert bps to price
        return expected_price * (bps / 10000.0)


@dataclass(frozen=True)
class RandomSlippage:
    """Random slippage within a range, useful for backtesting."""

    min_bps: float = 1.0
    max_bps: float = 20.0

    def estimate_slippage(
        self,
        expected_price: float,
        quantity: float,
        side: str,
        volatility: float | None = None,
        volume: float | None = None,
    ) -> float:
        bps = random.uniform(self.min_bps, self.max_bps)
        return expected_price * (bps / 10000.0)
