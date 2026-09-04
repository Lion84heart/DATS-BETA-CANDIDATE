"""Quantitative Research package (Sprint 6).

Research-only code. Nothing here is imported by, or wired into, any
live trading path. The trading engine, Strategy Engine, and execution
engine (trading/strategies/*, trading/execution/*, intelligence/fusion.py,
intelligence/engine.py, api/routers/execution.py, api/routers/orders.py)
are frozen this sprint and are used strictly read-only — imported and
replayed via the existing (also frozen) backtesting/BacktestEngine,
never modified.

This package's job is to run studies over that frozen stack and produce
comparative statistics — it introduces zero new trading strategies,
indicators, or fusion logic that could ever run live.
"""
