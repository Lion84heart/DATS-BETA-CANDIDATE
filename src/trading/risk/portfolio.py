"""Portfolio tracking and exposure management.

Tracks positions, exposures, correlations, and enforces limits
across the trading portfolio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np


@dataclass
class Position:
    """A single position in the portfolio."""

    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    side: str = "long"  # "long" or "short"
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    @property
    def market_value(self) -> float:
        """Current market value of the position."""
        mv = self.quantity * self.current_price
        return -mv if self.side == "short" else mv

    @property
    def notional(self) -> float:
        """Absolute notional value."""
        return abs(self.quantity * self.current_price)

    def update_price(self, new_price: float) -> None:
        """Update current price and recalculate unrealized P&L."""
        self.current_price = new_price
        if self.side == "long":
            self.unrealized_pnl = self.quantity * (new_price - self.entry_price)
        else:
            self.unrealized_pnl = self.quantity * (self.entry_price - new_price)


@dataclass
class ExposureLimit:
    """Exposure limit configuration."""

    max_position_pct: float = 0.20      # Max 20% in single position
    max_sector_pct: float = 0.40        # Max 40% in single sector
    max_portfolio_leverage: float = 2.0  # Max 2x leverage
    max_short_exposure_pct: float = 0.30  # Max 30% short
    min_cash_buffer_pct: float = 0.05   # Keep 5% cash


@dataclass
class PortfolioSnapshot:
    """Snapshot of portfolio state at a point in time."""

    timestamp: float
    total_value: float
    cash: float
    gross_exposure: float
    net_exposure: float
    long_exposure: float
    short_exposure: float
    unrealized_pnl: float
    realized_pnl: float
    positions: list[Position] = field(default_factory=list)


class PortfolioTracker:
    """Real-time portfolio tracking with exposure limits.

    Maintains positions, calculates exposures, and enforces
    configurable limits across the portfolio.
    """

    def __init__(
        self,
        initial_capital: float,
        exposure_limits: ExposureLimit | None = None,
    ):
        """Initialize portfolio tracker.

        Args:
            initial_capital: Starting capital.
            exposure_limits: Exposure limit configuration.
        """
        if initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.exposure_limits = exposure_limits or ExposureLimit()
        self._positions: dict[str, Position] = {}
        self._realized_pnl = 0.0
        self._history: list[PortfolioSnapshot] = []
        self._callbacks: list[Callable[[str, dict], None]] = []

    def add_position(self, position: Position) -> None:
        """Add or update a position.

        Args:
            position: Position to add.

        Raises:
            ValueError: If position would violate exposure limits.
        """
        # Check position limit
        total_value = self.total_value
        if total_value > 0:
            position_pct = position.notional / total_value
            if position_pct > self.exposure_limits.max_position_pct:
                raise ValueError(
                    f"Position {position.symbol} would be {position_pct:.2%} of portfolio, "
                    f"exceeds limit {self.exposure_limits.max_position_pct:.2%}"
                )

        # Check leverage
        gross = self.gross_exposure + position.notional
        if total_value > 0 and gross / total_value > self.exposure_limits.max_portfolio_leverage:
            raise ValueError(
                f"Position would increase leverage to {gross / total_value:.2f}x, "
                f"exceeds limit {self.exposure_limits.max_portfolio_leverage:.2f}x"
            )

        # Check short exposure
        if position.side == "short":
            new_short = self.short_exposure + position.notional
            if total_value > 0 and new_short / total_value > self.exposure_limits.max_short_exposure_pct:
                raise ValueError(
                    f"Short exposure would be {new_short / total_value:.2%}, "
                    f"exceeds limit {self.exposure_limits.max_short_exposure_pct:.2%}"
                )

        # Check cash buffer
        if position.side == "long":
            cost = position.quantity * position.entry_price
            if self.cash - cost < total_value * self.exposure_limits.min_cash_buffer_pct:
                raise ValueError(
                    f"Position would reduce cash below {self.exposure_limits.min_cash_buffer_pct:.2%} buffer"
                )
            self.cash -= cost

        self._positions[position.symbol] = position
        self._notify("position_added", {"symbol": position.symbol, "size": position.quantity})

    def remove_position(self, symbol: str) -> Position:
        """Remove a position and realize P&L.

        Args:
            symbol: Symbol to remove.

        Returns:
            The removed position.
        """
        if symbol not in self._positions:
            raise KeyError(f"Position {symbol} not found")
        pos = self._positions.pop(symbol)
        self._realized_pnl += pos.unrealized_pnl
        if pos.side == "long":
            self.cash += pos.quantity * pos.current_price
        self._notify("position_removed", {"symbol": symbol, "realized_pnl": pos.unrealized_pnl})
        return pos

    def update_prices(self, prices: dict[str, float]) -> None:
        """Update prices for all positions.

        Args:
            prices: Dict mapping symbol to current price.
        """
        for symbol, price in prices.items():
            if symbol in self._positions:
                self._positions[symbol].update_price(price)

    def snapshot(self, timestamp: float | None = None) -> PortfolioSnapshot:
        """Create a portfolio snapshot.

        Args:
            timestamp: Optional timestamp (defaults to current time).

        Returns:
            PortfolioSnapshot with current state.
        """
        import time as time_mod
        ts = timestamp if timestamp is not None else time_mod.time()

        positions = list(self._positions.values())
        unrealized = sum(p.unrealized_pnl for p in positions)
        long_exp = sum(p.market_value for p in positions if p.side == "long")
        short_exp = sum(abs(p.market_value) for p in positions if p.side == "short")
        gross = long_exp + short_exp
        net = long_exp - short_exp

        snap = PortfolioSnapshot(
            timestamp=ts,
            total_value=self.total_value,
            cash=self.cash,
            gross_exposure=gross,
            net_exposure=net,
            long_exposure=long_exp,
            short_exposure=short_exp,
            unrealized_pnl=unrealized,
            realized_pnl=self._realized_pnl,
            positions=positions,
        )
        self._history.append(snap)
        return snap

    def correlation_matrix(self, returns: dict[str, np.ndarray]) -> dict[str, dict[str, float]]:
        """Calculate correlation matrix between position returns.

        Args:
            returns: Dict mapping symbol to return array.

        Returns:
            Nested dict with correlation coefficients.
        """
        symbols = list(self._positions.keys())
        result: dict[str, dict[str, float]] = {s: {} for s in symbols}

        for i, s1 in enumerate(symbols):
            for s2 in symbols[i:]:
                if s1 in returns and s2 in returns:
                    r1, r2 = returns[s1], returns[s2]
                    min_len = min(len(r1), len(r2))
                    if min_len > 1:
                        corr = np.corrcoef(r1[:min_len], r2[:min_len])[0, 1]
                        if not np.isnan(corr):
                            result[s1][s2] = corr
                            result[s2][s1] = corr
        return result

    def exposure_report(self) -> dict:
        """Generate exposure report."""
        total = self.total_value
        if total == 0:
            return {"error": "Portfolio value is zero"}

        positions = list(self._positions.values())
        return {
            "total_value": total,
            "cash": self.cash,
            "cash_pct": self.cash / total,
            "gross_exposure": self.gross_exposure,
            "gross_leverage": self.gross_exposure / total,
            "net_exposure": self.net_exposure,
            "net_leverage": self.net_exposure / total,
            "long_exposure": self.long_exposure,
            "short_exposure": self.short_exposure,
            "short_pct": self.short_exposure / total,
            "unrealized_pnl": sum(p.unrealized_pnl for p in positions),
            "realized_pnl": self._realized_pnl,
            "position_count": len(positions),
            "largest_position": max((p.notional / total, p.symbol) for p in positions) if positions else (0.0, ""),
        }

    def on_event(self, callback: Callable[[str, dict], None]) -> None:
        """Register event callback."""
        self._callbacks.append(callback)

    def _notify(self, event: str, data: dict) -> None:
        """Notify callbacks."""
        for cb in self._callbacks:
            try:
                cb(event, data)
            except Exception:
                pass

    @property
    def total_value(self) -> float:
        """Total portfolio value (cash + positions)."""
        positions_value = sum(p.market_value for p in self._positions.values())
        return self.cash + positions_value

    @property
    def gross_exposure(self) -> float:
        """Total gross exposure (long + short)."""
        return sum(abs(p.market_value) for p in self._positions.values())

    @property
    def net_exposure(self) -> float:
        """Net exposure (long - short)."""
        return sum(p.market_value for p in self._positions.values())

    @property
    def long_exposure(self) -> float:
        """Total long exposure."""
        return sum(p.market_value for p in self._positions.values() if p.side == "long")

    @property
    def short_exposure(self) -> float:
        """Total short exposure."""
        return sum(abs(p.market_value) for p in self._positions.values() if p.side == "short")

    @property
    def history(self) -> list[PortfolioSnapshot]:
        """Return snapshot history."""
        return self._history.copy()
