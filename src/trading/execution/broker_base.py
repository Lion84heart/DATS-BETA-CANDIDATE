"""Broker execution interface.

Abstract base for broker connectivity. Supports both live trading
and paper trading modes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from trading.execution.orders import Order


@dataclass(frozen=True)
class BrokerOrderResult:
    """Result of submitting an order to a broker."""

    order_id: str
    status: str  # "pending", "filled", "partial", "rejected"
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    commission: float = 0.0
    slippage_bps: float = 0.0
    message: str = ""


@dataclass(frozen=True)
class BrokerPosition:
    """Position held at a broker."""

    symbol: str
    quantity: float
    avg_entry_price: float
    market_price: float
    unrealized_pnl: float
    realized_pnl: float


class BrokerConnector(ABC):
    """Abstract base for broker connectors.

    Implementations must provide order submission, fill tracking,
    and position queries.
    """

    def __init__(self, name: str, paper_mode: bool = False):
        """Initialize broker connector.

        Args:
            name: Broker identifier.
            paper_mode: If True, no real money at risk.
        """
        self.name = name
        self.paper_mode = paper_mode
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Whether broker is connected."""
        return self._connected

    @property
    def is_paper(self) -> bool:
        """Whether in paper trading mode."""
        return self.paper_mode

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to broker.

        Returns:
            True if connected.
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from broker."""
        ...

    @abstractmethod
    async def submit_order(self, order: Order) -> BrokerOrderResult:
        """Submit an order to the broker.

        Args:
            order: Order to submit.

        Returns:
            BrokerOrderResult with fill details.
        """
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order.

        Args:
            order_id: Order to cancel.

        Returns:
            True if cancellation was accepted.
        """
        ...

    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]:
        """Get all current positions.

        Returns:
            List of positions.
        """
        ...

    @abstractmethod
    async def get_account_value(self) -> float:
        """Get total account value.

        Returns:
            Account value in base currency.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if broker is configured and available."""
        ...

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize broker state."""
        ...
