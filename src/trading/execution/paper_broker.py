"""Paper trading broker implementation.

Simulates order fills using market price data without real capital
at risk. Uses slippage and commission models from production.
"""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass, field

from market.connectors.base import PriceTick
from trading.execution.broker_base import BrokerConnector, BrokerOrderResult, BrokerPosition
from trading.execution.fills import FillSimulator
from trading.execution.orders import Order, OrderSide, OrderStatus
from trading.execution.slippage import FixedSlippage


@dataclass
class PaperAccount:
    """Paper trading account state."""

    cash: float = 100000.0
    initial_capital: float = 100000.0
    positions: dict[str, BrokerPosition] = field(default_factory=dict)
    total_commission: float = 0.0
    total_slippage: float = 0.0

    @property
    def total_value(self) -> float:
        """Total account value (cash + positions)."""
        position_value = sum(
            pos.quantity * pos.market_price for pos in self.positions.values()
        )
        return self.cash + position_value

    @property
    def total_pnl(self) -> float:
        """Total P&L from initial capital."""
        return self.total_value - self.initial_capital

    @property
    def total_return_pct(self) -> float:
        """Total return percentage."""
        if self.initial_capital == 0:
            return 0.0
        return (self.total_pnl / self.initial_capital) * 100


class PaperBroker(BrokerConnector):
    """Paper trading broker — simulates fills without real money.

    Uses market price ticks to simulate fills with configurable
    slippage and commission models.
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission_per_trade: float = 1.0,
        slippage_bps: float = 2.0,
    ):
        """Initialize paper broker.

        Args:
            initial_capital: Starting capital.
            commission_per_trade: Fixed commission per trade.
            slippage_bps: Slippage in basis points.
        """
        super().__init__(name="paper", paper_mode=True)
        self.account = PaperAccount(
            cash=initial_capital, initial_capital=initial_capital
        )
        self._commission_per_trade = commission_per_trade
        self._slippage_bps = slippage_bps
        self._slippage = FixedSlippage()
        self._fill_simulator = FillSimulator(slippage_model=self._slippage)
        self._last_price: dict[str, float] = {}
        self._orders: dict[str, Order] = {}
        self._order_history: list[BrokerOrderResult] = []

    def on_price_tick(self, tick: PriceTick) -> None:
        """Update prices from market data feed.

        Args:
            tick: Latest price tick.
        """
        self._last_price[tick.symbol] = tick.price

        # Update position market prices
        if tick.symbol in self.account.positions:
            pos = self.account.positions[tick.symbol]
            updated = BrokerPosition(
                symbol=pos.symbol,
                quantity=pos.quantity,
                avg_entry_price=pos.avg_entry_price,
                market_price=tick.price,
                unrealized_pnl=(tick.price - pos.avg_entry_price) * pos.quantity,
                realized_pnl=pos.realized_pnl,
            )
            self.account.positions[tick.symbol] = updated

    async def connect(self) -> bool:
        """Paper broker always connects."""
        self._connected = True
        return True

    async def disconnect(self) -> None:
        """Paper broker disconnect is a no-op."""
        self._connected = False

    def _reject(self, order: Order, order_id: str, reason: str) -> BrokerOrderResult:
        """Record a rejected order and return its result.

        Rejections are tracked in ``_orders``/``_order_history`` alongside
        fills so order history/status reflect every real submission
        attempt, not just successful ones.
        """
        rejected = dataclasses.replace(order, order_id=order_id, status=OrderStatus.REJECTED)
        self._orders[order_id] = rejected
        result = BrokerOrderResult(order_id=order_id, status="rejected", message=reason)
        self._order_history.append(result)
        return result

    async def submit_order(self, order: Order) -> BrokerOrderResult:
        """Simulate order fill.

        Args:
            order: Order to simulate.

        Returns:
            BrokerOrderResult with simulated fill.
        """
        order_id = order.order_id or str(uuid.uuid4())
        order = dataclasses.replace(order, order_id=order_id)

        if order.symbol not in self._last_price:
            return self._reject(order, order_id, f"No price data for {order.symbol}")

        price = self._last_price[order.symbol]
        qty = float(order.quantity)

        # Apply slippage
        slippage_amount = self._slippage.estimate_slippage(price, qty, order.side)
        fill_price = price + slippage_amount if order.side == OrderSide.BUY else price - slippage_amount

        # Calculate commission
        commission = self._commission_per_trade

        # Calculate total cost
        total_cost = fill_price * qty + commission

        # Check buying power for buy orders
        if order.side == OrderSide.BUY and total_cost > self.account.cash:
            return self._reject(order, order_id, f"Insufficient cash: {self.account.cash} < {total_cost}")

        # Check held quantity for sell orders — paper trading has no shorting
        if order.side == OrderSide.SELL:
            held = self.account.positions.get(order.symbol)
            held_qty = held.quantity if held else 0.0
            if qty > held_qty:
                return self._reject(order, order_id, f"Cannot sell {qty} {order.symbol}: only {held_qty} held")

        # Update account cash
        if order.side == OrderSide.BUY:
            self.account.cash -= (fill_price * qty + commission)
        else:
            self.account.cash += (fill_price * qty - commission)
        self.account.total_commission += commission

        # Update position
        pos = self.account.positions.get(order.symbol)
        if pos:
            if order.side == OrderSide.BUY:
                new_qty = pos.quantity + qty
                new_avg = (pos.avg_entry_price * pos.quantity + fill_price * qty) / new_qty
                new_pnl = pos.realized_pnl
            else:
                # Sell — realize PnL
                new_qty = pos.quantity - qty
                realized = (fill_price - pos.avg_entry_price) * qty
                new_pnl = pos.realized_pnl + realized
                new_avg = pos.avg_entry_price if new_qty > 0 else 0.0

            if new_qty <= 0:
                self.account.positions.pop(order.symbol, None)
            else:
                self.account.positions[order.symbol] = BrokerPosition(
                    symbol=order.symbol,
                    quantity=new_qty,
                    avg_entry_price=new_avg,
                    market_price=fill_price,
                    unrealized_pnl=(fill_price - new_avg) * new_qty,
                    realized_pnl=new_pnl,
                )
        else:
            if order.side == OrderSide.BUY:
                self.account.positions[order.symbol] = BrokerPosition(
                    symbol=order.symbol,
                    quantity=qty,
                    avg_entry_price=fill_price,
                    market_price=fill_price,
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                )

        filled_order = order.with_fill(qty, fill_price)
        filled_order = dataclasses.replace(
            filled_order,
            metadata={**filled_order.metadata, "commission": commission},
        )
        self._orders[order_id] = filled_order

        result = BrokerOrderResult(
            order_id=order_id,
            status="filled",
            filled_qty=qty,
            avg_fill_price=fill_price,
            commission=commission,
            slippage_bps=self._slippage_bps,
            message=f"Paper filled at {fill_price}",
        )
        self._order_history.append(result)
        return result

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel is always accepted for paper trading."""
        return True

    async def get_positions(self) -> list[BrokerPosition]:
        """Get all positions."""
        return list(self.account.positions.values())

    async def get_account_value(self) -> float:
        """Get total account value."""
        return self.account.total_value

    def is_available(self) -> bool:
        """Paper broker is always available."""
        return True

    def to_dict(self) -> dict[str, Any]:
        """Serialize paper broker state."""
        return {
            "name": self.name,
            "paper_mode": self.paper_mode,
            "connected": self._connected,
            "cash": self.account.cash,
            "initial_capital": self.account.initial_capital,
            "total_value": self.account.total_value,
            "total_pnl": self.account.total_pnl,
            "total_return_pct": self.account.total_return_pct,
            "position_count": len(self.account.positions),
            "order_count": len(self._order_history),
            "commission_total": self.account.total_commission,
        }
