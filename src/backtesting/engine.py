"""Backtesting engine — replays historical bars through the live pipeline.

Reuses, without modification:
  - The eight Strategy Engine strategies (trading/strategies/*).
  - DecisionFusion (intelligence/fusion.py), exactly as used live.
  - PaperBroker (trading/execution/paper_broker.py) for trade simulation
    — the exact same fill/slippage/commission/no-shorting logic the
    live Paper Trading page uses, via a fresh, isolated instance (never
    the live registry's shared broker).

No new strategies or indicators. This module is purely: replay, decide
(via the existing engine), simulate, evaluate, report.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass
from typing import Any

import pandas as pd

from backtesting.confusion import ConfusionMatrix, compute_confusion_matrix
from backtesting.data import HistoricalBar
from backtesting.metrics import ClosedTrade, PortfolioMetrics, compute_portfolio_metrics
from intelligence.fusion import DecisionFusion
from market.connectors.base import PriceTick
from trading.base_strategy import BaseStrategy
from trading.execution.orders import Order, OrderSide, OrderType
from trading.execution.paper_broker import PaperBroker
from trading.schemas import SignalDirection, StrategySignal
from trading.strategies.atr import ATRStrategy
from trading.strategies.bollinger import BollingerBandsStrategy
from trading.strategies.ema_cross import EMACrossStrategy
from trading.strategies.rsi import RSIStrategy
from trading.strategies.support_resistance import SupportResistanceStrategy
from trading.strategies.trend_detection import TrendDetectionStrategy
from trading.strategies.volume_profile import VolumeProfileStrategy
from trading.strategies.vwap import VWAPStrategy

logger = logging.getLogger(__name__)

_MAX_WINDOW = 200  # same rolling bar-window cap as the live AI Decision Engine
_YIELD_EVERY_N_BARS = 50  # periodically yield to the event loop on long runs


def default_strategies() -> list[BaseStrategy]:
    """The same eight Strategy Engine members used live (Sprint 4)."""
    return [
        RSIStrategy(), EMACrossStrategy(), VWAPStrategy(), ATRStrategy(),
        BollingerBandsStrategy(), SupportResistanceStrategy(), VolumeProfileStrategy(),
        TrendDetectionStrategy(),
    ]


@dataclass(frozen=True)
class BacktestRunConfig:
    """Configuration for one backtest run."""

    symbol: str
    initial_capital: float = 100000.0
    position_size_pct: float = 0.95  # fraction of cash committed per BUY
    confusion_horizon_bars: int = 5
    confusion_threshold_pct: float = 0.1


@dataclass
class StrategyStat:
    """Per-strategy signal distribution, average confidence, and accuracy."""

    strategy: str
    buy_count: int = 0
    sell_count: int = 0
    hold_count: int = 0
    avg_confidence: float = 0.0
    confusion: ConfusionMatrix | None = None


@dataclass
class BacktestReport:
    """Complete result of one backtest run."""

    run_id: str
    symbol: str
    started_at: float
    completed_at: float
    num_bars: int
    initial_capital: float
    final_equity: float
    portfolio_metrics: PortfolioMetrics
    fusion_confusion: ConfusionMatrix
    per_strategy_stats: list[StrategyStat]
    trades: list[ClosedTrade]
    equity_curve: list[float]
    decisions: list[dict[str, Any]]


class BacktestEngine:
    """Replays OHLCV bars through the live Strategy Engine + Fusion + PaperBroker."""

    def __init__(
        self,
        strategies: list[BaseStrategy] | None = None,
        fusion: DecisionFusion | None = None,
    ) -> None:
        self.strategies = strategies or default_strategies()
        self.fusion = fusion or DecisionFusion()

    async def run(self, bars: list[HistoricalBar], config: BacktestRunConfig) -> BacktestReport:
        """Run one backtest and return the full report.

        Args:
            bars: Historical OHLCV bars, oldest first.
            config: Run configuration.

        Returns:
            BacktestReport with metrics, confusion stats, trades, and the
            full per-bar decision log.
        """
        started_at = time.time()
        broker = PaperBroker(initial_capital=config.initial_capital)

        window: list[dict[str, float]] = []
        equity_curve: list[float] = [config.initial_capital]
        fused_signals: list[str] = []
        closes: list[float] = []
        decisions_log: list[dict[str, Any]] = []
        strategy_signal_log: dict[str, list[StrategySignal]] = {s.name: [] for s in self.strategies}

        bars_in_position = 0
        open_trade: tuple[float, float, int] | None = None  # (entry_price, entry_time, entry_bar)
        closed_trades: list[ClosedTrade] = []

        for idx, bar in enumerate(bars):
            window.append(
                {"timestamp": bar.timestamp, "open": bar.open, "high": bar.high,
                 "low": bar.low, "close": bar.close, "volume": bar.volume}
            )
            if len(window) > _MAX_WINDOW:
                window.pop(0)
            df = pd.DataFrame(window)

            # Same tick-callback interface PaperBroker uses live.
            tick = PriceTick(
                symbol=config.symbol, timestamp=bar.timestamp, price=bar.close,
                bid=bar.close, ask=bar.close, volume=bar.volume, source="backtest",
            )
            broker.on_price_tick(tick)

            # Run every strategy — identical code path to the live engine.
            signals: list[StrategySignal] = []
            for strategy in self.strategies:
                try:
                    signal = strategy.generate_signal(df, features={})
                except Exception:
                    logger.exception("Strategy %s failed at bar %d", strategy.name, idx)
                    signal = None
                if signal is None:
                    signal = StrategySignal(
                        symbol=config.symbol, direction=SignalDirection.HOLD, confidence=0.0,
                        reason=f"{strategy.name} raised an error and produced no signal.",
                        strategy_name=strategy.name,
                    )
                signals.append(signal)
                strategy_signal_log[strategy.name].append(signal)

            fused = self.fusion.combine(signals)
            fused_signals.append(fused.direction.value)
            closes.append(bar.close)
            decisions_log.append(
                {
                    "bar": idx, "timestamp": bar.timestamp, "price": bar.close,
                    "signal": fused.direction.value, "confidence": fused.confidence,
                    "reasoning": fused.reasoning,
                }
            )

            # Simulate the trade via the exact live PaperBroker fill logic.
            held = broker.account.positions.get(config.symbol)
            held_qty = held.quantity if held else 0.0

            if fused.direction == SignalDirection.BUY and held_qty <= 0:
                qty = math.floor((broker.account.cash * config.position_size_pct) / bar.close) if bar.close > 0 else 0
                if qty > 0:
                    result = await broker.submit_order(
                        Order(symbol=config.symbol, side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=qty)
                    )
                    if result.status == "filled":
                        open_trade = (result.avg_fill_price, bar.timestamp, idx)
            elif fused.direction == SignalDirection.SELL and held_qty > 0:
                result = await broker.submit_order(
                    Order(symbol=config.symbol, side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=held_qty)
                )
                if result.status == "filled" and open_trade is not None:
                    entry_price, entry_ts, entry_bar = open_trade
                    pnl = (result.avg_fill_price - entry_price) * held_qty - result.commission
                    closed_trades.append(
                        ClosedTrade(
                            symbol=config.symbol, entry_time=entry_ts, exit_time=bar.timestamp,
                            entry_bar=entry_bar, exit_bar=idx, entry_price=entry_price,
                            exit_price=result.avg_fill_price, quantity=held_qty, pnl=pnl,
                            commission=result.commission,
                        )
                    )
                    open_trade = None

            if broker.account.positions.get(config.symbol):
                bars_in_position += 1

            equity_curve.append(broker.account.total_value)

            if idx % _YIELD_EVERY_N_BARS == 0:
                await asyncio.sleep(0)  # keep the event loop responsive on long runs

        # An open position at the end is reported as a mark-to-market
        # "closed" trade for statistics purposes only — the in-memory
        # backtest broker is discarded either way, so this never affects
        # any real state.
        held = broker.account.positions.get(config.symbol)
        if held and open_trade is not None:
            entry_price, entry_ts, entry_bar = open_trade
            last_bar = bars[-1]
            pnl = (last_bar.close - entry_price) * held.quantity
            closed_trades.append(
                ClosedTrade(
                    symbol=config.symbol, entry_time=entry_ts, exit_time=last_bar.timestamp,
                    entry_bar=entry_bar, exit_bar=len(bars) - 1, entry_price=entry_price,
                    exit_price=last_bar.close, quantity=held.quantity, pnl=pnl, commission=0.0,
                )
            )

        portfolio_metrics = compute_portfolio_metrics(
            equity_curve=equity_curve, trades=closed_trades, num_bars=len(bars),
            bars_in_position=bars_in_position, initial_capital=config.initial_capital,
        )

        fusion_confusion = compute_confusion_matrix(
            fused_signals, closes, horizon=config.confusion_horizon_bars,
            threshold_pct=config.confusion_threshold_pct,
        )

        per_strategy_stats: list[StrategyStat] = []
        for strategy in self.strategies:
            sigs = strategy_signal_log[strategy.name]
            preds = [s.direction.value for s in sigs]
            confs = [s.confidence for s in sigs]
            per_strategy_stats.append(
                StrategyStat(
                    strategy=strategy.name,
                    buy_count=preds.count("BUY"), sell_count=preds.count("SELL"), hold_count=preds.count("HOLD"),
                    avg_confidence=round(sum(confs) / len(confs), 4) if confs else 0.0,
                    confusion=compute_confusion_matrix(
                        preds, closes, horizon=config.confusion_horizon_bars,
                        threshold_pct=config.confusion_threshold_pct,
                    ),
                )
            )

        return BacktestReport(
            run_id=f"bt-{config.symbol}-{int(started_at * 1000)}",
            symbol=config.symbol, started_at=started_at, completed_at=time.time(),
            num_bars=len(bars), initial_capital=config.initial_capital,
            final_equity=equity_curve[-1], portfolio_metrics=portfolio_metrics,
            fusion_confusion=fusion_confusion, per_strategy_stats=per_strategy_stats,
            trades=closed_trades, equity_curve=equity_curve, decisions=decisions_log,
        )
