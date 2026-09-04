"""Historical Data Infrastructure (Phase 3).

Fetches, caches, validates, and converts real historical OHLCV market
data so it can feed the existing, unmodified
``backtesting.engine.BacktestEngine`` exactly like its synthetic and
CSV-import data sources already do.

Nothing here is imported by, or wired into, any live trading path. The
Trading Engine, Strategy Engine, and Decision Fusion
(``trading/strategies/*``, ``trading/execution/*``,
``intelligence/fusion.py``, ``intelligence/engine.py``) are frozen this
phase and are never imported by this package. ``backtesting/engine.py``
is also frozen and used strictly as a consumer — this package produces
``backtesting.data.HistoricalBar`` lists, the exact same type its
synthetic generator already produces, and hands them to
``BacktestEngine.run()`` unchanged.
"""
