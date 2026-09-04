"""Trade Management Intelligence (Phase 4).

A new execution-quality layer that sits *between* a fused BUY/SELL/HOLD
decision and the broker fill — deciding whether to act on an entry,
how much to size it, and when to actually exit (stop-loss, trailing
stop, break-even, or the original fused SELL signal). It never
generates a trading signal itself and never touches:

  - The Strategy Engine (``trading/strategies/*``) — frozen, unmodified.
  - Decision Fusion (``intelligence/fusion.py``) — frozen, unmodified,
    and used directly (not a substitute) everywhere in this package.
  - Any existing indicator's own computation — the ATR figure this
    package computes (``atr_utils.py``) is new, standalone
    risk-management plumbing that happens to reuse the same standard
    True-Range formula ``trading.strategies.atr.ATRStrategy`` already
    uses internally; it does not modify that file, and it never
    produces a BUY/SELL/HOLD signal or feeds Decision Fusion.

Every module here is built to be genuinely usable, not a one-off
research script — but per this phase's own mandate ("nothing goes live
unless statistically superior"), nothing in this package is imported
by, or wired into, any live trading path yet. ``managed_backtest.py``
is the backtesting harness used to decide whether any of it should be.
"""
