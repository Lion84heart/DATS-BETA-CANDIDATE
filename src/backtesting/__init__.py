"""Backtesting & Evaluation Framework.

Replays historical OHLCV data through the exact same Strategy Engine
(trading/strategies/*) and Decision Fusion (intelligence/fusion.py) used
live, and simulates trades via the exact same PaperBroker
(trading/execution/paper_broker.py) used for live paper trading — so a
backtest reflects precisely what the live system would have done over
the replayed period, not an approximate re-implementation.

No new strategies or indicators are introduced by this package — only
the ability to replay data through the existing ones, evaluate the
result, and report it.
"""
