"""Core execution engine.

Orchestrates order submission, fill simulation, execution strategies,
and integration with portfolio tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .fills import Fill, FillSimulator
from .order_lifecycle import OrderLifecycleManager
from .orders import Order, OrderSide, OrderStatus, OrderType
from .slippage import FixedSlippage


@dataclass
class ExecutionResult:
    """Result of order execution."""

    order: Order
    fills: list[Fill] = field(default_factory=list)
    avg_fill_price: float = 0.0
    total_filled: float = 0.0
    commission: float = 0.0
    pnl: float = 0.0


class ExecutionEngine:
    """Async execution engine for order management and fill simulation.

    Integrates order lifecycle, fill simulation, and execution strategies
    into a unified interface.
    """

    def __init__(
        self,
        fill_simulator: FillSimulator | None = None,
        commission_rate: float = 0.001,  # 10 bps
    ):
        """Initialize execution engine.

        Args:
            fill_simulator: Fill simulator for backtesting/paper trading.
            commission_rate: Commission as fraction of notional value.
        """
        self.lifecycle = OrderLifecycleManager()
        self.fill_simulator = fill_simulator or FillSimulator(
            slippage_model=FixedSlippage(amount=0.01, is_percentage=True)
        )
        self.commission_rate = commission_rate
        self._event_callbacks: list[Callable[[str, dict[str, Any]], None]] = []

    async def submit(self, order: Order) -> Order:
        """Submit an order for execution.

        Args:
            order: Order to submit.

        Returns:
            Registered order with assigned order_id and OPEN status.
        """
        registered = await self.lifecycle.register(order)
        updated = await self.lifecycle.transition(registered.order_id, OrderStatus.OPEN, "Order opened")
        self._notify("order_submitted", {"order_id": registered.order_id, "symbol": registered.symbol})
        return updated

    async def execute(
        self,
        order_id: str,
        market_price: float,
        market_volume: float | None = None,
        volatility: float | None = None,
    ) -> ExecutionResult:
        """Execute a single order against current market conditions.

        Args:
            order_id: Order to execute.
            market_price: Current market price.
            market_volume: Available market volume.
            volatility: Current volatility estimate.

        Returns:
            ExecutionResult with fills and statistics.
        """
        order = await self.lifecycle.get(order_id)
        if order is None:
            raise ValueError(f"Order {order_id} not found")

        fills: list[Fill] = []

        # Route to appropriate fill simulator
        if order.order_type == OrderType.MARKET:
            fill = self.fill_simulator.simulate_market_order(
                order, market_price, market_volume, volatility
            )
        elif order.order_type == OrderType.LIMIT:
            fill = self.fill_simulator.simulate_limit_order(
                order, market_price, market_volume, volatility
            )
        elif order.order_type == OrderType.STOP:
            fill = self.fill_simulator.simulate_stop_order(
                order, market_price, market_volume, volatility
            )
        else:
            # Default to market fill for unsupported types
            fill = self.fill_simulator.simulate_fill(
                order, market_price, market_volume, volatility
            )

        if fill:
            fills.append(fill)
            await self.lifecycle.fill(order_id, fill.quantity, fill.price)
            self._notify("order_filled", {
                "order_id": order_id,
                "fill_qty": fill.quantity,
                "fill_price": fill.price,
            })

        # Calculate execution statistics
        total_filled = sum(f.quantity for f in fills)
        avg_price = (
            sum(f.price * f.quantity for f in fills) / total_filled
            if total_filled > 0 else 0.0
        )
        notional = total_filled * avg_price
        commission = notional * self.commission_rate

        # Estimate PnL (simplified)
        pnl = 0.0
        if total_filled > 0:
            if order.side == OrderSide.BUY:
                pnl = (market_price - avg_price) * total_filled - commission
            else:
                pnl = (avg_price - market_price) * total_filled - commission

        updated = await self.lifecycle.get(order_id)
        return ExecutionResult(
            order=updated or order,
            fills=fills,
            avg_fill_price=avg_price,
            total_filled=total_filled,
            commission=commission,
            pnl=pnl,
        )

    async def cancel(self, order_id: str, reason: str = "User cancelled") -> Order | None:
        """Cancel an active order."""
        result = await self.lifecycle.cancel(order_id, reason)
        if result:
            self._notify("order_cancelled", {"order_id": order_id, "reason": reason})
        return result

    async def get_active_orders(self) -> list[Order]:
        """Return all active orders."""
        return await self.lifecycle.get_active()

    async def get_order(self, order_id: str) -> Order | None:
        """Get order by ID."""
        return await self.lifecycle.get(order_id)

    def on_event(self, callback: Callable[[str, dict[str, Any]], None]) -> None:
        """Register an event callback."""
        self._event_callbacks.append(callback)

    def _notify(self, event: str, data: dict[str, Any]) -> None:
        for cb in self._event_callbacks:
            try:
                cb(event, data)
            except Exception:
                pass

    async def get_statistics(self) -> dict[str, Any]:
        """Return execution statistics."""
        all_orders = await self.lifecycle.get_all()
        fills = self.fill_simulator.get_fills()

        filled_orders = [o for o in all_orders if o.status == OrderStatus.FILLED]
        cancelled_orders = [o for o in all_orders if o.status == OrderStatus.CANCELLED]
        rejected_orders = [o for o in all_orders if o.status == OrderStatus.REJECTED]

        total_notional = sum(f.price * f.quantity for f in fills)
        total_commission = total_notional * self.commission_rate

        return {
            "total_orders": len(all_orders),
            "filled_orders": len(filled_orders),
            "cancelled_orders": len(cancelled_orders),
            "rejected_orders": len(rejected_orders),
            "total_fills": len(fills),
            "total_filled_quantity": sum(f.quantity for f in fills),
            "total_notional": total_notional,
            "total_commission": total_commission,
            "fill_rate": len(filled_orders) / len(all_orders) if all_orders else 0.0,
        }
