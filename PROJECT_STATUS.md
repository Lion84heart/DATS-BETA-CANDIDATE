# DATS Beta — Project Status

**Last updated:** 2026-09-04 (Phase 2 complete)

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

**Backtesting & Evaluation Framework — new as of Sprint 5:**
- New **Backtesting** page: configure a symbol, a data source (synthetic-generated OHLCV or pasted real historical CSV), bar count, and initial capital, then run.
- Replays historical OHLCV bars through the **exact same** Strategy Engine (all 8 strategies, unmodified) and **exact same** `DecisionFusion` used live, and simulates trades via the **exact same** `PaperBroker` fill/commission/slippage/no-shorting logic Paper Trading uses — via a fresh, isolated broker instance created per run, never the live registry's shared broker. Verified: after multiple backtests generating dozens of simulated trades, the live portfolio remained untouched at exactly $100,000.00 cash with zero positions.
- Historical data: either **CSV import** of real OHLCV data (`timestamp,open,high,low,close,volume`) — literal replay of real market history — or **synthetic generation** via the existing `MarketSimulator` (the same GBM engine already driving live paper trading's price feed), sampling several intrabar sub-steps per bar to produce genuine open/high/low/close (unlike live's single-tick bars). Both paths verified working.
- Produces all 11 required metrics (Total Return, CAGR, Win Rate, Profit Factor, Sharpe, Sortino, Max Drawdown, Average Trade, Average Hold Time, Exposure, Number of Trades) via `backtesting/metrics.py` — standard, well-known formulas, bars-per-year=252 convention documented explicitly.
- Produces per-strategy statistics (signal distribution, average confidence, precision) and a fused-signal confusion matrix (predicted BUY/SELL/HOLD vs. actual subsequent price move, classified UP/DOWN/FLAT over a configurable forward horizon) — all hand-verified against the API's raw output for mathematical correctness.
- Every run is persisted (`data/decisions.db`, new `backtest_runs` table) — verified to survive a full container restart — and exportable as JSON or a multi-section CSV (summary metrics, confusion matrix, per-strategy stats, trades) via `GET /backtest/runs/{id}/export.{json,csv}`.
- Live Trading is unchanged: no live code path (execution.py, orders.py, the live broker/feed) was modified.

**Quantitative Research & Strategy Optimization — new as of Sprint 6:**
- Trading engine, Strategy Engine, and execution engine were frozen for the sprint — no new indicators, no new strategies, no changes to `intelligence/fusion.py`, `intelligence/engine.py`, `trading/strategies/*`, or any execution code. Verified via `git diff --name-only` scoped to every frozen path immediately before commit: zero changes.
- New `src/research/` package (research-only, never imported by any live path) ran a 243-run study — 216-run solo-strategy/fusion grid (8 symbols × 3 timeframes × 9 variants), 24-run fusion-method comparison, 3 large-scale (5,000-bar) flagship runs — entirely through the existing, unmodified `backtesting.BacktestEngine` (which already supported pluggable `strategies=`/`fusion=` constructor args from Sprint 5, so no engine change was needed).
- **Decision Fusion beats every individual strategy** on risk-adjusted return (avg Sharpe 0.568 vs. the best solo strategy, Volume Profile, at 0.527) — the clearest result of the study, confirming the ensemble's value over any single signal.
- **Weighted vs. majority voting compared honestly, not spun**: live confidence-weighted fusion and an optimized-weight variant tied at 3/8 symbol wins each; unweighted majority voting won 2/8. Reported as a near-tie requiring a larger sample before any weight change is adopted — see full nuance in the report.
- Produced a recommended per-strategy weight vector (data-grounded, e.g. VWAP 1.734, Volume Profile 1.595 highest; Trend Detection 0.285, EMA Cross 0.285 lowest) — **research output only, not applied to live trading**, since applying it would require editing the frozen `intelligence/fusion.py`.
- Symbol-specific and timeframe-specific breakdowns produced for all 8 symbols and all 3 timeframes (1H/1D/1W); 1H results are close to flat, most likely a fixed-250-bar warm-up-period artifact rather than evidence intraday doesn't work — flagged as an open question for a future study.
- Full raw results (`docs/sprint-6-research-results.json`) and the runner script (`scripts/run_quant_research.py`) are committed for reproducibility — the study is fully deterministic (fixed seed base) and can be re-run to reproduce every number in the report exactly.
- Full findings, methodology, and every table: [SPRINT-6-QUANT-REPORT.md](docs/SPRINT-6-QUANT-REPORT.md).

**Market Regime Engine — new as of Phase 2:**
- Trading engine, all 8 existing strategies, and Decision Fusion were frozen — no new indicators, no new strategies, no changes to `intelligence/fusion.py`, `trading/strategies/*`, or `backtesting/engine.py`. Verified via `git diff --name-only` scoped to every frozen path immediately before commit: zero changes.
- New `src/research/regime.py`: causal, bar-by-bar detection of 5 regimes (Trending Bull, Trending Bear, Sideways, High Volatility, Low Volatility) from trailing-window z-scored trend/volatility — no lookahead, defaults to Sideways until enough history exists.
- New `src/research/regime_router.py`: derives a per-regime, per-strategy routing weight vector from real backtested signal precision (reusing the frozen `backtesting.confusion.compute_confusion_matrix` unmodified), fit on one seed series and evaluated out-of-sample on a different one.
- New `src/research/regime_backtest.py`: a research-only backtest loop that reimplements `BacktestEngine.run()`'s exact trade-simulation semantics (same `PaperBroker`, same position-sizing) but selects fusion weights per-bar by detected regime — **verified via an automated sanity check to produce trade-for-trade identical output to the frozen `BacktestEngine` at neutral (1.0) weights**, confirming it's a faithful reimplementation, not a divergent one.
- **Honest result, not spun**: a 48-run comparison grid (8 symbols × 3 timeframes, static vs. regime-aware) shows regime-aware routing essentially tied on Sharpe (0.1723 vs. 0.1715), but *worse* on max drawdown (38.34% vs. 37.72%) and profit factor (1.144 vs. 1.228) than the current static system. **Recommendation: do not deploy regime-aware routing** — the underlying per-regime strategy "edge" scores driving the weights are thin (44%–55%, barely above coin-flip) on this phase's synthetic GBM data, which likely explains the near-tie.
- Full raw results (`docs/phase-2-regime-results.json`) and the runner script (`scripts/run_regime_research.py`) are committed for reproducibility.
- Full findings, methodology, and every table: [PHASE-2-REGIME-REPORT.md](docs/PHASE-2-REGIME-REPORT.md).

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
- Indicators that classically depend on intrabar high/low range (ATR, Support/Resistance) currently receive tick-derived bars with high=low=close (a single price tick carries no intrabar range) in **live** mode — the formulas are implemented against the full OHLC contract; **backtests now exercise the real thing**, since synthetic backtest bars have genuine open/high/low/close.
- Backtesting is single-symbol per run (no multi-asset portfolio backtest) and single-strategy-set (the fixed 8 — no UI to pick a subset or reweight the fusion).
- No walk-forward/out-of-sample split in the new Backtesting page (the codebase's separate, pre-existing `trading/backtest.py` has `run_walk_forward()` for single-strategy walk-forward testing, untouched by this sprint).
- Sprint 6's recommended per-strategy fusion weights are not applied to live `DecisionFusion` — the weighted-vs-majority comparison was a near-tie (§5 of the Sprint 6 report), so this is intentionally left as a future decision pending a larger-sample follow-up, not an oversight.
- Sprint 6's research grid uses a fixed 250-bar budget per (symbol, timeframe) run, which likely under-represents 1H performance (mature strategy warm-up needs more bars at finer timeframes) — a larger 1H-specific bar count is a natural follow-up, not yet done.
- Phase 2's Market Regime Engine is research-only and not applied to live trading or even to the frozen `BacktestEngine` — the 48-run comparison did not show a clear improvement over the static system (see the Phase 2 section above), so no routing change is recommended for deployment at this time. A follow-up on real historical OHLCV (via the existing `parse_csv_ohlcv` path) rather than synthetic GBM data is flagged as the most promising next step, not yet done.

## Sprint history

| Sprint | Focus | Report |
|---|---|---|
| — | Authentication fix (stale asset caching), initial CTO functional audit | [CTO-FUNCTIONAL-AUDIT-REPORT.md](docs/CTO-FUNCTIONAL-AUDIT-REPORT.md) |
| 1 | Truthfulness/production-safety pass — removed demo-data leaks, wired Dashboard/Trading/Health to real endpoints, fixed the Risk Status hardcode | [SPRINT-1-COMPLETION-REPORT.md](docs/SPRINT-1-COMPLETION-REPORT.md) |
| 2 | Paper Trading engine — real buy/sell, live positions, real-time P&L, closing positions, trade history | [SPRINT-2-COMPLETION-REPORT.md](docs/SPRINT-2-COMPLETION-REPORT.md) |
| 3 | AI Decision Engine — continuous BUY/SELL/HOLD analysis with confidence/reasoning/risk level, real SQLite persistence, advisory-only (no auto-execution) | [SPRINT-3-COMPLETION-REPORT.md](docs/SPRINT-3-COMPLETION-REPORT.md) |
| 4 | Strategy Engine — 8 independent technical-analysis strategies (RSI, EMA Cross, VWAP, ATR, Bollinger Bands, Support/Resistance, Volume Profile, Trend Detection) + Decision Fusion combining them, no LLMs/external AI | [SPRINT-4-COMPLETION-REPORT.md](docs/SPRINT-4-COMPLETION-REPORT.md) |
| 5 | Backtesting & Evaluation Framework — replays historical OHLCV through the exact live Strategy Engine/Fusion/PaperBroker, 11 metrics, per-strategy stats, confusion matrix, CSV/JSON export, new UI page | [SPRINT-5-COMPLETION-REPORT.md](docs/SPRINT-5-COMPLETION-REPORT.md) |
| 6 | Quantitative Research & Strategy Optimization — 243-run study over the frozen Strategy Engine/Fusion via the existing BacktestEngine: per-strategy comparison, fusion-vs-solo, weighted-vs-majority voting, symbol/timeframe breakdowns, recommended weights (research-only, not applied) | [SPRINT-6-QUANT-REPORT.md](docs/SPRINT-6-QUANT-REPORT.md) |
| Phase 2 | Market Regime Engine — causal 5-regime detection, empirically-derived regime routing weights, 48-run regime-aware-vs-static comparison (near-tie, not deployed), verified reimplementation of the frozen BacktestEngine's semantics | [PHASE-2-REGIME-REPORT.md](docs/PHASE-2-REGIME-REPORT.md) |
