"""Order lifecycle state machine.

Manages transitions between order states and enforces valid transitions.
Thread-safe via asyncio locks.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from .orders import Order, OrderStatus


class OrderLifecycleManager:
    """Manages order state transitions with validation and callbacks.

    Enforces valid state transitions:
    PENDING → OPEN → PARTIALLY_FILLED → FILLED
    OPEN → CANCELLED
    PENDING → REJECTED
    OPEN → EXPIRED
    """

    _VALID_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
        OrderStatus.PENDING: {
            OrderStatus.OPEN,
            OrderStatus.REJECTED,
        },
        OrderStatus.OPEN: {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
        },
        OrderStatus.PARTIALLY_FILLED: {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
        },
    }

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._lock = asyncio.Lock()
        self._callbacks: list[Callable[[Order, Order], None]] = []

    async def register(self, order: Order) -> Order:
        """Register a new order. Assigns order_id if not set."""
        async with self._lock:
            if not order.order_id:
                import uuid
                order = Order(
                    symbol=order.symbol,
                    side=order.side,
                    order_type=order.order_type,
                    quantity=order.quantity,
                    limit_price=order.limit_price,
                    stop_price=order.stop_price,
                    trailing_distance=order.trailing_distance,
                    trailing_type=order.trailing_type,
                    order_id=str(uuid.uuid4())[:12],
                    parent_order_id=order.parent_order_id,
                    metadata=order.metadata,
                )
            self._orders[order.order_id] = order
            return order

    async def transition(
        self, order_id: str, new_status: OrderStatus, reason: str = ""
    ) -> Order | None:
        """Transition an order to a new state.

        Args:
            order_id: The order to transition.
            new_status: Target state.
            reason: Human-readable reason for transition.

        Returns:
            Updated order, or None if order not found.

        Raises:
            ValueError: If the transition is invalid.
        """
        async with self._lock:
            current = self._orders.get(order_id)
            if current is None:
                return None

            valid = self._VALID_TRANSITIONS.get(current.status, set())
            if new_status not in valid and current.status != new_status:
                raise ValueError(
                    f"Invalid transition: {current.status.name} → {new_status.name}"
                )

            updated = current.with_status(new_status, reason)
            self._orders[order_id] = updated

        self._notify(current, updated)
        return updated

    async def fill(
        self, order_id: str, fill_qty: float, avg_price: float
    ) -> Order | None:
        """Record a fill against an order.

        Args:
            order_id: Order being filled.
            fill_qty: Quantity filled in this event.
            avg_price: Average price of this fill.

        Returns:
            Updated order, or None if not found.
        """
        async with self._lock:
            current = self._orders.get(order_id)
            if current is None:
                return None
            if current.remaining_quantity <= 0:
                return current

            updated = current.with_fill(fill_qty, avg_price)
            self._orders[order_id] = updated

        self._notify(current, updated)
        return updated

    async def cancel(self, order_id: str, reason: str = "User cancelled") -> Order | None:
        """Cancel an active order."""
        return await self.transition(order_id, OrderStatus.CANCELLED, reason)

    async def get(self, order_id: str) -> Order | None:
        """Get current state of an order."""
        async with self._lock:
            return self._orders.get(order_id)

    async def get_active(self) -> list[Order]:
        """Return all orders that can still be filled."""
        async with self._lock:
            return [o for o in self._orders.values() if o.is_active]

    async def get_all(self) -> list[Order]:
        """Return all orders."""
        async with self._lock:
            return list(self._orders.values())

    def on_transition(self, callback: Callable[[Order, Order], None]) -> None:
        """Register a callback for state transitions.

        The callback receives (old_order, new_order).
        """
        self._callbacks.append(callback)

    def _notify(self, old: Order, new: Order) -> None:
        for cb in self._callbacks:
            try:
                cb(old, new)
            except Exception:
                pass
