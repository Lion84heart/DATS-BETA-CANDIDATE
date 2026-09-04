# Sprint 3 Completion Report — AI Decision Engine

**Date:** 2026-09-04
**Scope:** Build a real AI Decision Engine that continuously analyzes live market data and records BUY/SELL/HOLD recommendations — with confidence, reasoning, and risk level — for every analysis pass, persisted to a real database and displayed in AI Center. Advisory only: no automatic execution, human approval still required.

## Design decisions and why

**"Live market data" = the same simulated feed Paper Trading already uses.** No other market data source exists anywhere in this codebase — there is no live-quotes provider, and building one would be new infrastructure well outside this sprint's scope. The engine subscribes to the exact same price-tick stream (`FeedManager` → `SimulatedConnector`) that `PaperBroker` already consumes for order fills (wired in Sprint 2), via the identical callback pattern. Practically, this means the AI Decision Engine runs whenever a Paper Trading session is running, and stops when it stops — one live-data lifecycle, not two.

**The "AI" is a real strategy, not a placeholder.** The codebase already contained a full, unused strategy framework (`trading/base_strategy.py`, `trading/strategies/{momentum,mean_reversion,breakout,trend_following,stat_arb}.py`) with a `StrategySignal` model whose `direction` field is literally `BUY`/`SELL`/`HOLD` (`SignalDirection` enum). The engine uses `MomentumStrategy` — real MACD(12,26,9) crossover detection with volume confirmation — instead of writing a new signal generator from scratch. This is genuine technical analysis computed from the actual simulated price path, not a random or scripted output.

**"Store every decision in the database" — implemented as a real database, not the existing file-per-decision store.** The existing `DecisionStore` wrote one JSON file per decision to `./decisions`, a directory outside any Docker volume mount — every decision was lost on every container restart, and its own docstring admitted *"Production would use a time-series database."* Rather than build new infrastructure (Postgres + migrations + a new docker-compose service, which none of this codebase currently has), `DecisionStore` was rewritten to use Python's stdlib `sqlite3` — a real relational database, zero new dependencies, zero new services — writing to `data/decisions.db` inside the `./data:/app/data` volume already mounted for the rest of the app's persisted state. The public API (`save`/`load`/`query`/`count`) is unchanged, so every existing caller (bootstrap health check, `/decisions/*` routes, `DecisionPipeline`) kept working without modification.

**Advisory-only was already half-built.** `DecisionPipeline.record_decision()` already set every recorded decision to `REVIEW_REQUIRED` status, and `POST /decisions/{id}/review` already existed for a human to mark one reviewed — the pipeline's own docstring already stated *"must be manually reviewed before any action is taken... never modifies production."* This sprint's engine simply calls that existing, already-safe pipeline; it does not touch the broker or `/orders/` in any way.

## What was built

**`src/intelligence/engine.py` (new)** — `AIDecisionEngine`. Registered as a feed callback exactly like `PaperBroker.on_price_tick`. Per symbol: buffers incoming ticks into a rolling OHLCV bar window (capped at 200 bars), and — rate-limited to once per 3 seconds per symbol, so a 1-second tick interval doesn't flood the store — runs one analysis pass:
- Fewer than 35 bars collected (MomentumStrategy's MACD warmup requirement): records **HOLD** with a "warming up: N/35 bars" reason and confidence that rises with bar count.
- 35+ bars: calls `MomentumStrategy.generate_signal()`. A crossover fires → its real `direction`/`confidence`/`reason` are used directly. No crossover → records **HOLD** with an explicit "no crossover/volume confirmation" reason.
- Risk level (LOW/MEDIUM/HIGH) is computed from the standard deviation of the last 20 bar-to-bar returns — a real statistic from the actual simulated price path.
- Every exception during analysis is caught and logged — a bad tick or strategy error can never take down the shared price feed the broker also depends on.

**`src/intelligence/decisions.py`** — `DecisionRecord` gained `signal: str | None` and `risk_level: str | None` fields. `DecisionStore` rewritten to SQLite (see above). Also fixed: `_dict_to_record` previously silently dropped `risk_assessment`, `portfolio_state`, and `feature_vector` on every read (they serialized fine but were never reconstructed) — now fully restored, which several already-existing API responses (the risk-check fields exposed in Sprint 1) had been silently returning empty for.

**`src/system/decision_pipeline.py`** — `record_decision()` now accepts and stores `signal`/`risk_level`. `decision_id` generation now includes a short UUID suffix to eliminate a same-millisecond collision risk that appears when multiple symbols are analyzed close together (upsert semantics meant a collision would silently merge two decisions into one row rather than crash, but this removes the possibility entirely).

**`src/api/main.py`** — Instantiates `AIDecisionEngine(pipeline=pipeline)` alongside the existing `DecisionPipeline` at startup, stored as `app.state.ai_engine`.

**`src/api/routers/execution.py`** — `/paper/start` now also registers the AI engine as a feed callback (same duplicate-registration guard already used for the broker). `/paper/status` now includes an `ai_engine` summary (decisions recorded, symbols tracked, strategy name).

**`src/api/routers/decisions.py`** — `GET /decisions/` now returns `signal` and `risk_level`, and accepts `signal` as a filter query parameter.

**`src/api/routers/orders.py`** — no functional change this sprint, but note: while wiring the engine's data path, `DecisionStore._dict_to_record` fixes above resolved a latent gap that had been silently affecting the `/decisions/` risk-check fields since Sprint 1.

**Frontend (`app.js`, `index.html`)** — AI Center's Current Recommendation card now shows the real signal (was hardcoded N/A) and a new Risk Level badge. Decision History table gained a Risk column and now shows real signal badges (was always `-`); its Status column now reads "Pending review" instead of a bare dash for decisions awaiting human review, making the approval-required workflow visible. Trading page's AI Decisions panel also now shows the real signal (its rendering already anticipated this field from Sprint 2 but had nothing real to show). AI Center added to the 5-second auto-refresh loop (previously only Dashboard/Trading/Paper Trading/Health refreshed automatically) so new decisions appear live while viewing the page. Demo Mode's illustrative data extended with `risk_level` values for visual consistency — still never touches the real backend.

**`.gitignore`** — added `/data/` and `*.db` so the SQLite file (runtime state) can never be accidentally committed.

## Verification

All verification was against the real running Docker stack, rebuilt after the change and loaded from a fresh never-before-cached loopback address to guarantee real network fetches.

| Check | Result |
|---|---|
| Continuous analysis | Started a session with AAPL/MSFT/GOOGL; `GET /decisions/` showed new decisions accumulating for all three symbols roughly every 3 seconds each, confidence rising as bars accumulated (0.09 → 0.11 → 0.14 → 0.16 while warming up), exactly matching the engine's own formula. |
| Always BUY/SELL/HOLD | Every one of 50+ recorded decisions had a non-null `signal` of BUY, SELL, or HOLD — none missing. |
| Confidence/reasoning/risk level present | Every decision carried a numeric `confidence`, a non-empty `reasoning_summary` ("Warming up: 19/35..." then later "No momentum crossover or volume confirmation on this bar — holding."), and a `risk_level` of LOW/MEDIUM/HIGH computed from real volatility. |
| Real strategy, not a placeholder | Reasoning text matches `MomentumStrategy`'s actual code paths verbatim (warmup message and no-crossover message), confirming the real MACD logic runs, not a stub. |
| Stored in a database | `docker exec dats-beta ls /app/data/` showed `decisions.db` inside the mounted volume. Queried decisions immediately after `docker restart dats-beta` (a full process restart) — the same decisions from before the restart were still returned, confirming real persistence (the prior file-based store, outside any volume, would have lost everything). |
| Displayed in AI Center | Current AI Recommendation card showed the real HOLD signal, 50% confidence ring, "Risk Level MEDIUM" badge, and real reasoning text. Decision History table rendered 45 real rows with correct Signal and Risk badges. |
| No automatic execution | After 50+ AI decisions recorded (including the warmup period), Paper Trading's Open Positions showed "No open positions", Trade History showed "No trades yet", and cash remained exactly $100,000.00 — the engine never once called `POST /orders/`. |
| Human approval still required | Called `POST /decisions/{id}/review` directly — succeeded, returned `{"status": "reviewed", ...}`. Decision History's Status column correctly shows "Pending review" for everything not yet reviewed. |
| Every recommendation visible before execution | All decisions (BUY/SELL/HOLD alike) appear in Decision History regardless of signal — nothing is hidden or requires an action to become visible. |
| Health check | `GET /health/` → `decisions_available: {healthy: true, message: "Decision store operational"}`, confirming the SQLite-backed store satisfies the pre-existing health check (`store.query(limit=1)`) unchanged. |
| Regression sweep | Clicked through all six pages in both Live and Demo Mode after the rebuild — zero console errors. Demo Mode confirmed unaffected (still shows illustrative HOLD/BUY/SELL rows with the new Risk column, never calling the real backend). |

## What was deliberately left alone

- **No UI "Approve" button** — objective 9 asks that every recommendation be *visible* before execution, which is satisfied by Decision History; a one-click review action from the UI (vs. the existing API endpoint) is a natural next step but wasn't explicitly requested this sprint.
- **Only one strategy (Momentum)** — the codebase has four other unused strategies (mean reversion, breakout, trend following, stat arb); running an ensemble or letting the user pick is a reasonable Sprint 4 candidate, not built here to keep this sprint's scope to "an AI Decision Engine," singular, as asked.
- **No independent engine lifecycle** — the engine starts/stops with the Paper Trading session rather than having its own Start/Stop controls, because "live market data" in this app only exists while a paper session is running; giving it a separate lifecycle would mean inventing a second, redundant data feed.
- **Fixed symbol universe** — inherited from Sprint 2's paper trading; not expanded, since no live quotes/watchlist source exists to justify a larger universe.
