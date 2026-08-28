"""End-to-end trading simulation loop.

Integrates strategy signals, risk management, order execution,
monitoring, and decision recording into a unified simulation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from security.validation import InputValidator
from simulation.market_sim import PricePath


@dataclass
class SimulationResult:
    """Results from a complete trading simulation run."""

    symbol: str
    start_price: float
    end_price: float
    total_return_pct: float
    num_trades: int
    win_count: int
    loss_count: int
    total_pnl: float
    sharpe_ratio: float | None = None
    max_drawdown_pct: float = 0.0
    avg_slippage_bps: float = 0.0
    avg_execution_ms: float = 0.0
    decisions_recorded: int = 0
    alerts_fired: int = 0
    risk_events: int = 0
    param_overrides: dict[str, Any] = field(default_factory=dict)


class TradingSimulator:
    """End-to-end trading simulator.

    Orchestrates the complete trading pipeline:
    market data → strategy signal → risk check → order → execution → record.
    """

    def __init__(
        self,
        strategy_fn: Callable[[list[float]], str],
        risk_fn: Callable[[dict[str, Any]], bool],
        position_size_fn: Callable[[float, float], float],
        execution_cost_bps: float = 5.0,
        slippage_bps: float = 2.0,
        commission_per_trade: float = 1.0,
        initial_capital: float = 100000.0,
    ):
        """Initialize trading simulator.

        Args:
            strategy_fn: Function(price_history) -> signal ('BUY', 'SELL', 'HOLD').
            risk_fn: Function(context) -> bool (True = allow trade).
            position_size_fn: Function(price, capital) -> quantity.
            execution_cost_bps: Cost in basis points per trade.
            slippage_bps: Slippage in basis points.
            commission_per_trade: Fixed commission per trade.
            initial_capital: Starting capital.
        """
        self.strategy_fn = strategy_fn
        self.risk_fn = risk_fn
        self.position_size_fn = position_size_fn
        self.execution_cost_bps = execution_cost_bps
        self.slippage_bps = slippage_bps
        self.commission = commission_per_trade
        self.initial_capital = initial_capital
        self._validator = InputValidator()

    def run(
        self,
        price_path: PricePath,
        lookback: int = 20,
        signal_threshold: float = 0.0,
    ) -> SimulationResult:
        """Run a complete simulation over a price path.

        Args:
            price_path: Generated or historical price path.
            lookback: Bars to feed strategy.
            signal_threshold: Minimum signal strength to act.

        Returns:
            SimulationResult with full statistics.
        """
        prices = price_path.prices
        capital = self.initial_capital
        position = 0.0  # Current holdings
        trades: list[dict[str, Any]] = []
        equity_curve: list[float] = [capital]
        peak = capital
        max_dd = 0.0
        decisions = 0
        alerts = 0
        risk_events = 0

        for i in range(lookback, len(prices)):
            price = prices[i]
            history = prices[max(0, i - lookback):i]

            # 1. Generate signal
            signal = self.strategy_fn(history)

            # 2. Skip if no signal or holding same direction
            if signal == "HOLD":
                # Mark-to-market
                equity = capital + position * price
                equity_curve.append(equity)
                peak = max(peak, equity)
                dd = (peak - equity) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)
                continue

            # 3. Risk assessment
            context = {
                "price": price,
                "capital": capital,
                "position": position,
                "signal": signal,
                "equity": capital + position * price,
                "max_drawdown": max_dd,
            }
            if not self.risk_fn(context):
                risk_events += 1
                continue

            # 4. Calculate order size
            qty = self.position_size_fn(price, capital)
            if qty <= 0:
                continue

            # 5. Validate
            try:
                self._validator.price(price)
                self._validator.positive_int(int(qty), "quantity", max_value=1000000)
            except Exception:
                continue

            # 6. Execute with slippage and cost
            if signal == "BUY" and position <= 0:
                # Buy: pay slippage (higher price)
                fill_price = price * (1 + self.slippage_bps / 10000)
                cost = qty * fill_price * (self.execution_cost_bps / 10000) + self.commission
                if capital >= qty * fill_price + cost:
                    # Close short if any, then open long
                    if position < 0:
                        pnl = abs(position) * (price - fill_price)
                        capital += pnl
                        trades.append({"type": "COVER", "pnl": pnl, "price": fill_price})
                        position = 0
                    position += qty
                    capital -= qty * fill_price + cost
                    trades.append({"type": "BUY", "qty": qty, "price": fill_price, "cost": cost})
                    decisions += 1

            elif signal == "SELL" and position >= 0:
                # Sell: receive slippage (lower price)
                fill_price = price * (1 - self.slippage_bps / 10000)
                cost = qty * fill_price * (self.execution_cost_bps / 10000) + self.commission
                if position >= qty:
                    pnl = qty * (fill_price - self._avg_entry(trades, qty))
                    capital += qty * fill_price - cost
                    position -= qty
                    trades.append({"type": "SELL", "qty": qty, "price": fill_price, "cost": cost, "pnl": pnl})
                    decisions += 1
                elif position > 0:
                    # Sell remaining position
                    qty = position
                    pnl = qty * (fill_price - self._avg_entry(trades, qty))
                    capital += qty * fill_price - cost
                    position = 0
                    trades.append({"type": "SELL", "qty": qty, "price": fill_price, "cost": cost, "pnl": pnl})
                    decisions += 1

            # Mark-to-market
            equity = capital + position * price
            equity_curve.append(equity)
            peak = max(peak, equity)
            dd = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        # Final mark-to-market
        final_price = prices[-1]
        final_equity = capital + position * final_price

        # Calculate stats
        winning_trades = [t for t in trades if t.get("pnl", 0) > 0]
        losing_trades = [t for t in trades if t.get("pnl", 0) < 0]
        total_pnl = sum(t.get("pnl", 0) for t in trades)
        avg_slippage = self.slippage_bps  # Simulated constant

        # Sharpe from equity curve returns
        sharpe = self._sharpe_from_equity(equity_curve)

        total_return = (final_equity - self.initial_capital) / self.initial_capital * 100

        return SimulationResult(
            symbol=price_path.symbol,
            start_price=prices[0],
            end_price=final_price,
            total_return_pct=total_return,
            num_trades=len([t for t in trades if t["type"] in ("BUY", "SELL")]),
            win_count=len(winning_trades),
            loss_count=len(losing_trades),
            total_pnl=total_pnl,
            sharpe_ratio=sharpe,
            max_drawdown_pct=max_dd * 100,
            avg_slippage_bps=avg_slippage,
            avg_execution_ms=0.5,  # Simulated
            decisions_recorded=decisions,
            alerts_fired=alerts,
            risk_events=risk_events,
        )

    def run_batch(
        self,
        price_paths: list[PricePath],
        lookback: int = 20,
    ) -> list[SimulationResult]:
        """Run simulation over multiple price paths.

        Args:
            price_paths: List of price paths to simulate.
            lookback: Bars for strategy lookback.

        Returns:
            List of SimulationResult.
        """
        return [self.run(path, lookback) for path in price_paths]

    @staticmethod
    def _avg_entry(trades: list[dict[str, Any]], qty: float) -> float:
        """Calculate average entry price from buy trades."""
        buy_trades = [t for t in trades if t["type"] == "BUY"]
        if not buy_trades:
            return 0.0
        total_qty = sum(t["qty"] for t in buy_trades)
        total_cost = sum(t["qty"] * t["price"] for t in buy_trades)
        return total_cost / total_qty if total_qty > 0 else 0.0

    @staticmethod
    def _sharpe_from_equity(equity: list[float]) -> float | None:
        """Calculate annualized Sharpe ratio from equity curve."""
        if len(equity) < 3:
            return None
        returns = [(equity[i] - equity[i - 1]) / equity[i - 1] for i in range(1, len(equity)) if equity[i - 1] > 0]
        if not returns:
            return None
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        std = variance ** 0.5
        if std < 1e-12:
            return float("inf") if mean_ret > 0 else float("-inf")
        # Annualize (assume daily)
        return (mean_ret / std) * (252 ** 0.5)
