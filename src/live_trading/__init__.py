"""Live Paper Trading pipeline.

Connects the existing, frozen Strategy Engine and Decision Fusion to
real live market data (via ``market.connectors.binance_live``) and
Phase 4's already-built (not yet deployed) risk-management stack, and
submits the resulting decisions as real paper trades through the
shared ``PaperBroker`` — the same broker every other part of this app
already uses. Never touches real money: the market-data connector is
structurally read-only public data, and the only broker in this
codebase, paper or otherwise, is the simulated one.

No strategy is modified, no parameter is tuned here — every threshold
and multiplier is Phase 4's own untuned default. This package observes
how the existing engine behaves on real live data; it does not
optimize anything.
"""
