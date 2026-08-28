"""Execution strategies for large orders.

Implements TWAP, VWAP, and iceberg execution to minimize
market impact on large trades.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .orders import Order, OrderType


@dataclass(frozen=True)
class ExecutionSlice:
    """A single slice of a larger execution strategy."""

    quantity: float
    order_type: OrderType
    limit_price: float | None = None
    delay_seconds: float = 0.0


class ExecutionStrategy(ABC):
    """Base class for execution strategies."""

    @abstractmethod
    def slice_order(self, order: Order, num_slices: int = 5) -> list[ExecutionSlice]:
        """Break an order into execution slices.

        Args:
            order: The parent order to slice.
            num_slices: Number of slices (default 5).

        Returns:
            List of execution slices.
        """
        ...


class TWAPStrategy(ExecutionStrategy):
    """Time-Weighted Average Price execution.

    Divides order into equal-sized slices executed at regular
    time intervals over a specified duration.
    """

    def __init__(self, duration_seconds: float = 300.0):
        """Initialize TWAP strategy.

        Args:
            duration_seconds: Total execution duration (default 5 minutes).
        """
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        self.duration_seconds = duration_seconds

    def slice_order(self, order: Order, num_slices: int = 5) -> list[ExecutionSlice]:
        slice_qty = order.remaining_quantity / num_slices
        delay = self.duration_seconds / num_slices
        return [
            ExecutionSlice(
                quantity=slice_qty,
                order_type=OrderType.MARKET,
                delay_seconds=delay * i,
            )
            for i in range(num_slices)
        ]


class VWAPStrategy(ExecutionStrategy):
    """Volume-Weighted Average Price execution.

    Sizes slices proportionally to historical volume profile.
    Larger slices during high-volume periods.
    """

    def __init__(self, volume_profile: list[float] | None = None):
        """Initialize VWAP strategy.

        Args:
            volume_profile: Relative volume weights for each time bucket.
                Defaults to equal weighting.
        """
        self.volume_profile = volume_profile or [1.0] * 5
        total = sum(self.volume_profile)
        if total == 0:
            raise ValueError("volume_profile must not sum to zero")
        self._normalized = [v / total for v in self.volume_profile]

    def slice_order(self, order: Order, num_slices: int = 5) -> list[ExecutionSlice]:
        if num_slices != len(self._normalized):
            # Normalize to num_slices
            profile = self._normalized[:num_slices]
            if len(profile) < num_slices:
                profile += [1.0 / len(self._normalized)] * (num_slices - len(profile))
            total = sum(profile)
            weights = [w / total for w in profile]
        else:
            weights = self._normalized

        slices = []
        for i, weight in enumerate(weights):
            slice_qty = order.remaining_quantity * weight
            slices.append(
                ExecutionSlice(
                    quantity=slice_qty,
                    order_type=OrderType.LIMIT,
                    delay_seconds=60.0 * i,
                )
            )
        return slices


class IcebergStrategy(ExecutionStrategy):
    """Iceberg / hidden quantity execution.

    Shows only a small visible quantity while keeping the
    majority hidden. Refreshes visible quantity as it fills.
    """

    def __init__(self, visible_quantity: float | None = None):
        """Initialize iceberg strategy.

        Args:
            visible_quantity: Displayed quantity per slice.
                Defaults to 10% of total order.
        """
        self.visible_quantity = visible_quantity

    def slice_order(self, order: Order, num_slices: int = 5) -> list[ExecutionSlice]:
        visible = self.visible_quantity or max(order.remaining_quantity * 0.1, 1.0)
        slices = []
        remaining = order.remaining_quantity
        while remaining > 0:
            qty = min(visible, remaining)
            slices.append(
                ExecutionSlice(
                    quantity=qty,
                    order_type=OrderType.LIMIT,
                    delay_seconds=0.0 if len(slices) == 0 else 30.0,
                )
            )
            remaining -= qty
        return slices
