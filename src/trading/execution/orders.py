"""Order types and order book representation.

Implements the foundational order model used by the execution engine.
Orders are immutable once created; status changes produce new Order instances
via the lifecycle manager.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any


class OrderSide(Enum):
    """Order direction."""

    BUY = auto()
    SELL = auto()


class OrderType(Enum):
    """Order execution type."""

    MARKET = auto()
    LIMIT = auto()
    STOP = auto()
    STOP_LIMIT = auto()
    TRAILING_STOP = auto()


class OrderStatus(Enum):
    """Lifecycle state of an order."""

    PENDING = auto()
    OPEN = auto()
    PARTIALLY_FILLED = auto()
    FILLED = auto()
    CANCELLED = auto()
    REJECTED = auto()
    EXPIRED = auto()


@dataclass(frozen=True, slots=True)
class Order:
    """An immutable order request."""

    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    filled_quantity: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    limit_price: float | None = None
    stop_price: float | None = None
    trailing_distance: float | None = None
    trailing_type: str = "percent"  # "percent" or "absolute"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None
    order_id: str = ""
    parent_order_id: str | None = None  # For child orders (e.g. iceberg slices)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.filled_quantity < 0:
            raise ValueError("filled_quantity must be non-negative")
        if self.filled_quantity > self.quantity:
            raise ValueError("filled_quantity cannot exceed quantity")
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("LIMIT orders require limit_price")
        if self.order_type in (OrderType.STOP, OrderType.STOP_LIMIT) and self.stop_price is None:
            raise ValueError("STOP and STOP_LIMIT orders require stop_price")
        if self.order_type == OrderType.STOP_LIMIT and self.limit_price is None:
            raise ValueError("STOP_LIMIT orders require both stop_price and limit_price")
        if self.order_type == OrderType.TRAILING_STOP and self.trailing_distance is None:
            raise ValueError("TRAILING_STOP orders require trailing_distance")

    @property
    def remaining_quantity(self) -> float:
        """Quantity yet to be filled."""
        return self.quantity - self.filled_quantity

    @property
    def is_complete(self) -> bool:
        """True if order is fully filled, cancelled, rejected, or expired."""
        return self.status in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        }

    @property
    def is_active(self) -> bool:
        """True if order can still be filled."""
        return self.status in {
            OrderStatus.OPEN,
            OrderStatus.PARTIALLY_FILLED,
        }

    @property
    def fill_percent(self) -> float:
        """Percentage of order that has been filled."""
        if self.quantity == 0:
            return 0.0
        return (self.filled_quantity / self.quantity) * 100.0

    def with_fill(self, filled_qty: float, avg_price: float) -> "Order":
        """Return a new Order with updated fill information.

        Args:
            filled_qty: Additional quantity filled in this update.
            avg_price: Average fill price for the new quantity.

        Raises:
            ValueError: If filled_qty would exceed remaining quantity.
        """
        if filled_qty > self.remaining_quantity:
            raise ValueError(
                f"Fill quantity {filled_qty} exceeds remaining {self.remaining_quantity}"
            )
        new_filled = self.filled_quantity + filled_qty
        new_status = (
            OrderStatus.FILLED
            if new_filled >= self.quantity
            else OrderStatus.PARTIALLY_FILLED
        )
        return Order(
            symbol=self.symbol,
            side=self.side,
            order_type=self.order_type,
            quantity=self.quantity,
            filled_quantity=new_filled,
            status=new_status,
            limit_price=self.limit_price,
            stop_price=self.stop_price,
            trailing_distance=self.trailing_distance,
            trailing_type=self.trailing_type,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc),
            order_id=self.order_id,
            parent_order_id=self.parent_order_id,
            metadata={
                **self.metadata,
                "avg_fill_price": avg_price,
                "last_fill_qty": filled_qty,
                "last_fill_time": datetime.now(timezone.utc).isoformat(),
            },
        )

    def with_status(self, status: OrderStatus, reason: str = "") -> "Order":
        """Return a new Order with updated status."""
        return Order(
            symbol=self.symbol,
            side=self.side,
            order_type=self.order_type,
            quantity=self.quantity,
            filled_quantity=self.filled_quantity,
            status=status,
            limit_price=self.limit_price,
            stop_price=self.stop_price,
            trailing_distance=self.trailing_distance,
            trailing_type=self.trailing_type,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc),
            order_id=self.order_id,
            parent_order_id=self.parent_order_id,
            metadata={**self.metadata, "status_reason": reason},
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize order to dictionary."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.name,
            "order_type": self.order_type.name,
            "quantity": self.quantity,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "status": self.status.name,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "trailing_distance": self.trailing_distance,
            "trailing_type": self.trailing_type,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "fill_percent": self.fill_percent,
            "is_active": self.is_active,
            "is_complete": self.is_complete,
            "metadata": self.metadata,
        }
