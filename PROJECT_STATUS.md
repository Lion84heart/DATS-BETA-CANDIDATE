# DATS Beta — Project Status

**Last updated:** 2026-09-04 (Sprint 4 complete)

This is a living snapshot of what actually works in the running application today, maintained alongside each sprint. For narrative history of *why* things changed, see the sprint completion reports in `docs/`. For the original full audit this roadmap is derived from, see `docs/CTO-FUNCTIONAL-AUDIT-REPORT.md`.

## What works today

**Authentication** — Real login (`admin`/`admin` and other seeded roles), JWT + session, RBAC. Demo Mode is a separate, clearly-labeled illustrative path that never touches the real backend.

**Dashboard** — Portfolio value, P&L, buying power, and open positions read the real paper broker (`GET /portfolio/`). Risk Status / Kill Switch / Max Drawdown / Daily Loss read the real kill-switch component (`GET /status/risk`) instead of a hardcoded "always safe" display. AI Engine status and decision counts read the real decision store. Market open/closed is computed from real NYSE trading hours.

**Trading (page)** — Orders and Positions tabs read the real broker. Risk Panel reads real thresholds. AI Decisions panel and Closed tab correctly show nothing fake when Demo Mode is off (previously leaked demo data unconditionally — fixed in Sprint 1). BUY/SELL buttons on this specific page are still inert — manual order entry was built on the **Paper Trading** page in Sprint 2 instead (see below); wiring this page's buttons to the same order flow is a small follow-up, not yet done.

**Paper Trading — fully functional as of Sprint 2:**
- **Start/Stop Session** streams real simulated market prices (via the existing `SimulatedConnector` + `FeedManager`) into the same paper broker every other page reads from — a single, consistent account, not a disconnected simulation.
- **Buy/Sell** submits real market orders (`POST /orders/`) that fill against live simulated prices, with real slippage and commission.
- **Positions** are created, updated, and P&L is recalculated in real time as prices tick (5-second UI poll; broker-side price updates are continuous while a session is running).
- **Close** on any open position submits an offsetting sell for the full held quantity.
- **Trade History** shows every real order attempt — filled and rejected (insufficient cash, insufficient position, no price data yet) — pulled from `GET /orders/history`.
- Selling short and real-money trading are both structurally impossible: sells are capped at held quantity, and the broker is `PaperBroker` (`paper_mode=True`) with no live-broker integration anywhere in the code path.

**System Health** — Service Status now correctly maps to the real `GET /health/` check names (previously mismatched, always showed "UNKNOWN" regardless of true status — fixed in Sprint 1). Performance Metrics renders the real metrics snapshot. Memory/CPU/API Latency bars are still hardcoded — no real host-metrics endpoint exists without adding a new dependency (`psutil`), intentionally deferred.

**Reports** — Entirely out of scope so far. No backend exists (zero `/report*` endpoints anywhere). Not silently faked; the page is left as a known gap.

**AI Decision Engine + Strategy Engine — Strategy Engine added in Sprint 4:**
- Runs automatically whenever a Paper Trading session is active, analyzing the same live simulated price ticks the broker fills orders against (`intelligence/engine.py`, subscribed to the feed exactly like `PaperBroker.on_price_tick`).
- **Eight independent, modular strategies** (`trading/strategies/{rsi,ema_cross,vwap,atr,bollinger,support_resistance,volume_profile,trend_detection}.py`), each a deterministic, rule-based technical-analysis computation over real price/volume data — RSI, EMA crossover, VWAP deviation, ATR volatility breakout, Bollinger Bands, Support/Resistance proximity, Volume Profile (point of control), and linear-regression Trend Detection. No LLM, no OpenAI, no Claude, no external AI API anywhere in this codebase. Each strategy always returns BUY, SELL, or HOLD with its own confidence and reasoning — never silently skips an analysis pass, even with insufficient history (records an honest low-confidence HOLD instead).
- **Decision Fusion** (`intelligence/fusion.py`) combines all eight strategies' independent votes into one final recommendation via confidence-weighted majority voting — a transparent, auditable arithmetic rule, not a black box. `MomentumStrategy` (Sprint 3's original single strategy) remains in the codebase but is no longer part of the live fusion; the Strategy Engine replaced it as of this sprint.
- Every analysis pass records exactly one **fused** decision — BUY, SELL, or HOLD — with a confidence score (0–1), fusion reasoning (which strategies voted which way and by how much), and a categorical risk level (LOW/MEDIUM/HIGH, computed from real recent price volatility) — plus all eight individual strategy results behind it, each separately persisted.
- **Advisory only — verified.** After 270+ fused decisions (2,160+ individual strategy results) recorded across a running session, cash and positions were unchanged and trade history was empty: nothing here ever calls `POST /orders/`. Every decision is created with `REVIEW_REQUIRED` status (`DecisionPipeline`), and `POST /decisions/{id}/review` (pre-existing endpoint) lets a human mark one reviewed. A human must act through the separate, existing manual Buy/Sell flow to execute anything.
- Decisions and strategy results are stored in a real SQLite database (`data/decisions.db`, `decisions` and `strategy_results` tables, inside the same mounted volume as the rest of the app's persisted state) — verified to survive a full container restart.
- Displayed in AI Center: Current AI Recommendation (fused signal, confidence, risk level, fusion reasoning), a new **Strategy Engine Breakdown** table (every one of the 8 strategies' independent signal/confidence/reasoning behind the current recommendation, via `GET /decisions/{id}/strategies`), and Decision History (every fused decision, status shown as "Pending review" until a human reviews it).

## Known gaps (not yet done, tracked from the audit)

- Trading page BUY/SELL buttons not wired (Paper Trading page covers manual trading for now).
- No live market-data/watchlist quotes (only the simulated paper-trading feed).
- No realized-P&L "closed positions" history distinct from the paper trading order history.
- Reports page has no backend.
- Memory/CPU/API Latency real host metrics (needs `psutil`).
- "● Live" badge and the two real WebSocket endpoints (`/ws/decisions`, `/ws/market`) exist server-side but nothing in the frontend connects to them yet — all updates are still 5-second polling.
- AI Center's `target_price`/`stop_loss` fields have no source anywhere in the backend's decision data model — shown honestly as N/A, not fabricated. (`signal` is now real as of Sprint 3.)
- Paper Trading Pause has no backend capability (button exists, does nothing).
- No UI button yet to mark a decision reviewed from AI Center — the `POST /decisions/{id}/review` endpoint exists and works, just isn't wired to a click.
- The Strategy Engine/AI Decision Engine starts/stops with the Paper Trading session rather than having its own independent lifecycle (no other live market-data source exists to analyze).
- Strategy Engine runs against a fixed symbol universe (inherited from Paper Trading) — no live quotes/watchlist source exists to justify a larger one.
- Indicators that classically depend on intrabar high/low range (ATR, Support/Resistance) currently receive tick-derived bars with high=low=close (a single price tick carries no intrabar range) — the formulas are implemented against the full OHLC contract and are forward-compatible with real OHLC bars, but today they're a documented simplification, not a limitation of the math itself.

## Sprint history

| Sprint | Focus | Report |
|---|---|---|
| — | Authentication fix (stale asset caching), initial CTO functional audit | [CTO-FUNCTIONAL-AUDIT-REPORT.md](docs/CTO-FUNCTIONAL-AUDIT-REPORT.md) |
| 1 | Truthfulness/production-safety pass — removed demo-data leaks, wired Dashboard/Trading/Health to real endpoints, fixed the Risk Status hardcode | [SPRINT-1-COMPLETION-REPORT.md](docs/SPRINT-1-COMPLETION-REPORT.md) |
| 2 | Paper Trading engine — real buy/sell, live positions, real-time P&L, closing positions, trade history | [SPRINT-2-COMPLETION-REPORT.md](docs/SPRINT-2-COMPLETION-REPORT.md) |
| 3 | AI Decision Engine — continuous BUY/SELL/HOLD analysis with confidence/reasoning/risk level, real SQLite persistence, advisory-only (no auto-execution) | [SPRINT-3-COMPLETION-REPORT.md](docs/SPRINT-3-COMPLETION-REPORT.md) |
| 4 | Strategy Engine — 8 independent technical-analysis strategies (RSI, EMA Cross, VWAP, ATR, Bollinger Bands, Support/Resistance, Volume Profile, Trend Detection) + Decision Fusion combining them, no LLMs/external AI | [SPRINT-4-COMPLETION-REPORT.md](docs/SPRINT-4-COMPLETION-REPORT.md) |
