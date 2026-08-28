"""DATS — Event-Driven Backtesting Engine.

Walks through OHLCV data bar-by-bar, computing features and generating signals
with no look-ahead bias. Models transaction costs (commission + slippage).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from trading.base_strategy import BaseStrategy
from trading.schemas import (
    BacktestResult,
    PerformanceMetrics,
    SignalDirection,
    TradeRecord,
)

logger = logging.getLogger(__name__)


class BacktestEngine:
    """Event-driven backtesting engine with transaction cost modeling.

    Configuration:
        initial_capital: Starting capital (default: 10000.0)
        commission_rate: Commission per trade as decimal (default: 0.001 = 0.1%)
        slippage_model: 'fixed' or 'percentage' (default: 'fixed')
        slippage: Slippage amount (default: 0.0005 = 0.05%)
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission_rate: float = 0.001,
        slippage_model: str = "fixed",
        slippage: float = 0.0005,
    ) -> None:
        self.initial_capital: float = initial_capital
        self.commission_rate: float = commission_rate
        self.slippage_model: str = slippage_model
        self.slippage: float = slippage

    def _apply_slippage(self, price: float, direction: SignalDirection) -> float:
        """Apply slippage to a price based on the slippage model."""
        if self.slippage_model == "fixed":
            slippage_amount = self.slippage
        elif self.slippage_model == "percentage":
            slippage_amount = price * self.slippage
        else:
            slippage_amount = 0.0

        if direction == SignalDirection.BUY:
            return price + slippage_amount
        elif direction == SignalDirection.SELL:
            return price - slippage_amount
        return price

    def _compute_fees(self, price: float, size: float) -> float:
        """Compute total fees for a trade."""
        notional = price * size
        return notional * self.commission_rate

    def run(
        self,
        strategy: BaseStrategy,
        ohlcv_df: pd.DataFrame,
    ) -> BacktestResult:
        """Run a backtest walk-forward through OHLCV data.

        Args:
            strategy: The strategy to backtest.
            ohlcv_df: OHLCV DataFrame with columns open, high, low, close, volume.

        Returns:
            BacktestResult with full metrics, equity curve, and trades.
        """
        if ohlcv_df.empty or len(ohlcv_df) < 30:
            logger.warning("Insufficient OHLCV data for backtest: %d rows", len(ohlcv_df))
            return self._empty_result(strategy, ohlcv_df)

        from data.features import FeatureEngine

        feature_engine = FeatureEngine()
        capital = self.initial_capital
        equity_curve: list[float] = [capital]
        trades: list[TradeRecord] = []
        position: float = 0.0  # positive = long, negative = short
        entry_price: float | None = None
        entry_time: datetime | None = None
        current_trade: TradeRecord | None = None
        trade_count = 0

        # Walk bar by bar — NO look-ahead
        for i in range(30, len(ohlcv_df)):
            current_bar = ohlcv_df.iloc[i]
            history = ohlcv_df.iloc[: i + 1].copy()

            # Compute features using only data up to current bar
            features = feature_engine.compute_features(history)

            # Add close price for strategies that need it
            features["close"] = float(current_bar["close"])
            features["volume"] = float(current_bar["volume"])

            # Generate signal
            signal = strategy.generate_signal(history, features)

            price = float(current_bar["close"])
            timestamp = current_bar.name if hasattr(current_bar, "name") else pd.Timestamp(history.index[-1])
            if isinstance(timestamp, str):
                timestamp = pd.Timestamp(timestamp)

            if signal is not None and signal.direction != SignalDirection.HOLD:
                # Determine trade direction
                if signal.direction == SignalDirection.BUY and position <= 0:
                    # Close short / open long
                    if position < 0 and current_trade is not None:
                        # Close short
                        exit_price = self._apply_slippage(price, SignalDirection.BUY)
                        pnl = (current_trade.entry_price - exit_price) * current_trade.size
                        fees = self._compute_fees(exit_price, current_trade.size) + self._compute_fees(
                            current_trade.entry_price, current_trade.size
                        )
                        current_trade.exit_time = timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else datetime.now(timezone.utc)
                        current_trade.exit_price = exit_price
                        current_trade.pnl = pnl - fees
                        current_trade.fees = fees
                        capital += pnl - fees
                        trades.append(current_trade)
                        current_trade = None

                    # Open long
                    if position <= 0:
                        entry_price = self._apply_slippage(price, SignalDirection.BUY)
                        size = capital / entry_price * 0.95  # Use 95% of capital
                        fees = self._compute_fees(entry_price, size)
                        capital -= fees
                        position = size
                        trade_count += 1
                        current_trade = TradeRecord(
                            entry_time=timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else datetime.now(timezone.utc),
                            entry_price=entry_price,
                            size=size,
                            direction="long",
                            fees=fees,
                            signal_id=f"signal_{trade_count}",
                        )

                elif signal.direction == SignalDirection.SELL and position >= 0:
                    # Close long / open short
                    if position > 0 and current_trade is not None:
                        # Close long
                        exit_price = self._apply_slippage(price, SignalDirection.SELL)
                        pnl = (exit_price - current_trade.entry_price) * current_trade.size
                        fees = self._compute_fees(exit_price, current_trade.size) + self._compute_fees(
                            current_trade.entry_price, current_trade.size
                        )
                        current_trade.exit_time = timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else datetime.now(timezone.utc)
                        current_trade.exit_price = exit_price
                        current_trade.pnl = pnl - fees
                        current_trade.fees = fees
                        capital += pnl - fees
                        trades.append(current_trade)
                        current_trade = None

                    # Open short
                    if position >= 0:
                        entry_price = self._apply_slippage(price, SignalDirection.SELL)
                        size = capital / entry_price * 0.95
                        fees = self._compute_fees(entry_price, size)
                        capital -= fees
                        position = -size
                        trade_count += 1
                        current_trade = TradeRecord(
                            entry_time=timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else datetime.now(timezone.utc),
                            entry_price=entry_price,
                            size=size,
                            direction="short",
                            fees=fees,
                            signal_id=f"signal_{trade_count}",
                        )

            # Mark-to-market equity
            if position > 0 and current_trade is not None:
                unrealized = (price - current_trade.entry_price) * position
                equity = capital + unrealized
            elif position < 0 and current_trade is not None:
                unrealized = (current_trade.entry_price - price) * abs(position)
                equity = capital + unrealized
            else:
                equity = capital
            equity_curve.append(equity)

        # Close any open position at the end
        if current_trade is not None and current_trade.is_open():
            last_bar = ohlcv_df.iloc[-1]
            last_price = float(last_bar["close"])
            last_timestamp = ohlcv_df.index[-1]
            if isinstance(last_timestamp, str):
                last_timestamp = pd.Timestamp(last_timestamp)

            if current_trade.direction == "long":
                exit_price = self._apply_slippage(last_price, SignalDirection.SELL)
                pnl = (exit_price - current_trade.entry_price) * current_trade.size
            else:
                exit_price = self._apply_slippage(last_price, SignalDirection.BUY)
                pnl = (current_trade.entry_price - exit_price) * current_trade.size

            fees = self._compute_fees(exit_price, current_trade.size)
            current_trade.exit_time = last_timestamp.to_pydatetime() if hasattr(last_timestamp, "to_pydatetime") else datetime.now(timezone.utc)
            current_trade.exit_price = exit_price
            current_trade.pnl = pnl - fees
            current_trade.fees += fees
            capital += pnl - fees
            trades.append(current_trade)
            equity_curve[-1] = capital

        # Compute metrics
        metrics = self._compute_metrics(trades, equity_curve)

        start_date = ohlcv_df.index[0]
        end_date = ohlcv_df.index[-1]
        if isinstance(start_date, str):
            start_date = pd.Timestamp(start_date)
        if isinstance(end_date, str):
            end_date = pd.Timestamp(end_date)

        total_return = (equity_curve[-1] - self.initial_capital) / self.initial_capital if self.initial_capital > 0 else 0.0

        return BacktestResult(
            strategy_name=strategy.name,
            symbol=strategy.config.symbol,
            start_date=start_date.to_pydatetime() if hasattr(start_date, "to_pydatetime") else datetime.now(timezone.utc),
            end_date=end_date.to_pydatetime() if hasattr(end_date, "to_pydatetime") else datetime.now(timezone.utc),
            total_return=total_return,
            sharpe_ratio=metrics.sharpe_ratio,
            max_drawdown=metrics.max_drawdown,
            win_rate=metrics.win_rate,
            num_trades=metrics.num_trades,
            avg_trade_return=total_return / max(1, metrics.num_trades),
            profit_factor=metrics.profit_factor,
            equity_curve=equity_curve,
            trades=trades,
            parameters=strategy.get_parameters(),
            metrics=metrics,
        )

    def _compute_equity_curve(self, trades: list[TradeRecord]) -> list[float]:
        """Reconstruct equity curve from trades."""
        equity = [self.initial_capital]
        for trade in trades:
            equity.append(equity[-1] + trade.pnl)
        return equity

    def _compute_metrics(
        self, trades: list[TradeRecord], equity: list[float]
    ) -> PerformanceMetrics:
        """Compute comprehensive performance metrics."""
        if not trades:
            return PerformanceMetrics()

        # Trade returns
        trade_returns = [t.pnl for t in trades if t.pnl != 0]
        if not trade_returns:
            return PerformanceMetrics()

        wins = [r for r in trade_returns if r > 0]
        losses = [r for r in trade_returns if r <= 0]

        total_return = sum(trade_returns)
        win_rate = len(wins) / len(trade_returns) if trade_returns else 0.0

        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        avg_win = np.mean(wins) if wins else 0.0
        avg_loss = np.mean(losses) if losses else 0.0

        expectancy = (win_rate * avg_win - (1 - win_rate) * abs(avg_loss)) if trade_returns else 0.0

        # Equity curve metrics
        equity_array = np.array(equity)
        returns = np.diff(equity_array) / equity_array[:-1]
        returns = returns[np.isfinite(returns)]

        # Sharpe ratio (annualized, assuming ~252 trading days)
        if len(returns) > 1 and returns.std() > 0:
            sharpe = (returns.mean() / returns.std()) * np.sqrt(252)
        else:
            sharpe = 0.0

        # Sortino ratio
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0 and downside_returns.std() > 0:
            sortino = (returns.mean() / downside_returns.std()) * np.sqrt(252)
        else:
            sortino = 0.0

        # Max drawdown and duration
        peak = equity_array[0]
        max_dd = 0.0
        dd_duration = 0
        max_dd_duration = 0
        current_dd_duration = 0

        for val in equity_array:
            if val > peak:
                peak = val
                current_dd_duration = 0
            else:
                dd = (peak - val) / peak if peak > 0 else 0
                current_dd_duration += 1
                if dd > max_dd:
                    max_dd = dd
                    max_dd_duration = max(max_dd_duration, current_dd_duration)

        # Calmar ratio
        total_ret = (equity_array[-1] - self.initial_capital) / self.initial_capital if self.initial_capital > 0 else 0.0
        n_days = max(len(equity) / (24 * 60), 1)  # Assuming 1m bars
        annualized_ret = (1 + total_ret) ** (252 / max(n_days, 1)) - 1 if n_days > 0 and total_ret > -1 else total_ret
        calmar = annualized_ret / max_dd if max_dd > 0 else 0.0

        # Volatility
        if len(returns) > 1:
            volatility = returns.std() * np.sqrt(252)
            skew = float(pd.Series(returns).skew()) if len(returns) > 2 else 0.0
            kurt = float(pd.Series(returns).kurtosis()) if len(returns) > 3 else 0.0
        else:
            volatility = 0.0
            skew = 0.0
            kurt = 0.0

        # Avg holding period
        holding_periods = []
        for t in trades:
            if t.exit_time is not None and t.entry_time is not None:
                try:
                    dt = (t.exit_time - t.entry_time).total_seconds() / 60.0
                    holding_periods.append(dt)
                except (TypeError, AttributeError):
                    pass
        avg_holding = np.mean(holding_periods) if holding_periods else 0.0

        return PerformanceMetrics(
            total_return=total_return,
            annualized_return=annualized_ret,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            max_drawdown_duration=max_dd_duration,
            calmar_ratio=calmar,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            expectancy=expectancy,
            num_trades=len(trades),
            avg_holding_period=avg_holding,
            volatility=volatility,
            skewness=skew,
            kurtosis=kurt,
        )

    def _empty_result(
        self, strategy: BaseStrategy, ohlcv_df: pd.DataFrame
    ) -> BacktestResult:
        """Return an empty backtest result."""
        now = datetime.now(timezone.utc)
        return BacktestResult(
            strategy_name=strategy.name,
            symbol=strategy.config.symbol,
            start_date=now,
            end_date=now,
            equity_curve=[self.initial_capital],
            parameters=strategy.get_parameters(),
        )

    def run_walk_forward(
        self,
        strategy: BaseStrategy,
        ohlcv_df: pd.DataFrame,
        train_size: int,
        test_size: int,
    ) -> list[BacktestResult]:
        """Run walk-forward backtest: train on [0:train], test on [train:train+test].

        Args:
            strategy: Strategy to backtest.
            ohlcv_df: Full OHLCV DataFrame.
            train_size: Number of bars for the initial training window.
            test_size: Number of bars for each test window.

        Returns:
            List of BacktestResult objects, one per walk-forward window.
        """
        results: list[BacktestResult] = []
        start_idx = train_size

        while start_idx + test_size <= len(ohlcv_df):
            test_df = ohlcv_df.iloc[start_idx : start_idx + test_size]
            result = self.run(strategy, test_df)
            results.append(result)
            start_idx += test_size

        return results
