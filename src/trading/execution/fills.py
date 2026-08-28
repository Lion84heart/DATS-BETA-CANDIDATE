"""Fill simulation for backtesting and paper trading.

Simulates order fills based on market data, slippage models, and
liquidity assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .orders import Order, OrderSide, OrderStatus
from .slippage import SlippageModel


@dataclass(frozen=True)
class Fill:
    """A single fill event."""

    order_id: str
    symbol: str
    quantity: float
    price: float
    timestamp: datetime
    side: str


class FillSimulator:
    """Simulates order fills against market data.

    Supports partial fills based on available volume and
    configurable fill probability.
    """

    def __init__(
        self,
        slippage_model: SlippageModel,
        fill_probability: float = 1.0,
        partial_fill_enabled: bool = True,
    ):
        """Initialize fill simulator.

        Args:
            slippage_model: Model for estimating price slippage.
            fill_probability: Probability of fill (0-1).
            partial_fill_enabled: Whether to allow partial fills.
        """
        if not 0 <= fill_probability <= 1:
            raise ValueError("fill_probability must be in [0, 1]")
        self.slippage_model = slippage_model
        self.fill_probability = fill_probability
        self.partial_fill_enabled = partial_fill_enabled
        self._fills: list[Fill] = []

    def simulate_fill(
        self,
        order: Order,
        market_price: float,
        market_volume: float | None = None,
        volatility: float | None = None,
    ) -> Fill | None:
        """Simulate a fill for an order.

        Args:
            order: The order to fill.
            market_price: Current market price.
            market_volume: Available market volume (for partial fills).
            volatility: Current volatility estimate.

        Returns:
            Fill event if filled, None if not filled.
        """
        if not order.is_active and order.status != OrderStatus.PENDING:
            return None

        # Check fill probability
        import random
        if random.random() > self.fill_probability:
            return None

        # Determine fill quantity
        remaining = order.remaining_quantity
        if self.partial_fill_enabled and market_volume is not None:
            fill_qty = min(remaining, market_volume * 0.3)  # Fill up to 30% of volume
        else:
            fill_qty = remaining

        if fill_qty <= 0:
            return None

        # Calculate fill price with slippage
        slippage = self.slippage_model.estimate_slippage(
            expected_price=market_price,
            quantity=fill_qty,
            side=order.side.name,
            volatility=volatility,
            volume=market_volume,
        )

        # Adverse slippage: buy higher, sell lower
        if order.side == OrderSide.BUY:
            fill_price = market_price + slippage
        else:
            fill_price = market_price - slippage

        fill = Fill(
            order_id=order.order_id,
            symbol=order.symbol,
            quantity=fill_qty,
            price=fill_price,
            timestamp=datetime.now(timezone.utc),
            side=order.side.name,
        )
        self._fills.append(fill)
        return fill

    def simulate_market_order(
        self,
        order: Order,
        market_price: float,
        market_volume: float | None = None,
        volatility: float | None = None,
    ) -> Fill | None:
        """Simulate a market order fill.

        Market orders have higher fill probability but worse slippage.
        """
        return self.simulate_fill(order, market_price, market_volume, volatility)

    def simulate_limit_order(
        self,
        order: Order,
        market_price: float,
        market_volume: float | None = None,
        volatility: float | None = None,
    ) -> Fill | None:
        """Simulate a limit order fill.

        Only fills if market price is at or better than limit price.
        """
        if order.limit_price is None:
            return None

        # Check if price is favorable
        if order.side == OrderSide.BUY and market_price > order.limit_price:
            return None  # Market price above buy limit
        if order.side == OrderSide.SELL and market_price < order.limit_price:
            return None  # Market price below sell limit

        return self.simulate_fill(order, market_price, market_volume, volatility)

    def simulate_stop_order(
        self,
        order: Order,
        market_price: float,
        market_volume: float | None = None,
        volatility: float | None = None,
    ) -> Fill | None:
        """Simulate a stop order fill.

        Triggers when market price crosses stop price, then fills as market order.
        """
        if order.stop_price is None:
            return None

        # Check if stop triggered
        triggered = False
        if order.side == OrderSide.BUY and market_price >= order.stop_price:
            triggered = True
        if order.side == OrderSide.SELL and market_price <= order.stop_price:
            triggered = True

        if not triggered:
            return None

        return self.simulate_fill(order, market_price, market_volume, volatility)

    def get_fills(self, order_id: str | None = None) -> list[Fill]:
        """Get fill history.

        Args:
            order_id: Optional filter by order ID.
        """
        if order_id is None:
            return self._fills.copy()
        return [f for f in self._fills if f.order_id == order_id]
