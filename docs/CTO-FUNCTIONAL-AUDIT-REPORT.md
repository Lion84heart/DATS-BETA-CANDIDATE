# CTO Functional Audit Report — DATS Beta Dashboard

**Date:** 2026-09-03
**Scope:** Every screen, widget, and button reachable from the authenticated dashboard (`src/api/static/index.html` + `app.js`), cross-referenced against the actual backend routers in `src/api/routers/`.
**Method:** Static review of `app.js` (what each widget actually renders and which endpoints it calls, if any) against every FastAPI router, verified by reading route implementations directly — not by assumption.
**Precondition:** Authentication is now fixed and verified working (see prior fix, commit `3af6dc0`). This report assumes login succeeds and covers everything *behind* the login screen.

## How to read this report

Each item is classified as exactly one of:

| Status | Meaning |
|---|---|
| **Working** | Real frontend interaction, calls a real backend endpoint, verified to function. |
| **Frontend only** | Renders using hardcoded/demo data or client-side-only logic. A working backend endpoint may exist but is never called. |
| **Backend missing** | No API endpoint exists to serve this widget's data — even a wired frontend would have nothing real to call. |
| **Placeholder** | Static decorative content, explicitly not real (e.g. "chart placeholder" text), not wired to anything by design. |
| **Not implemented** | No frontend event handler *and* no backend capability. Clicking/using it does nothing at all. |

## Cross-cutting finding (applies to every page)

The topbar's **"● Live"** status indicator is always on — there is no WebSocket connection anywhere in `app.js` (confirmed: zero references to `WebSocket` in the file), despite the backend exposing two real, working WebSocket endpoints (`/ws/decisions`, `/ws/market`, in `src/api/routers/websocket.py`). Every "Real-time" / "Live" label on the dashboard (positions, risk metrics, activity log) is aspirational copy, not a real data channel. The only refresh mechanism is a 5-second `setInterval` polling loop, and even that only re-renders demo data or the `/health/` endpoint — nothing else.

---

## 1. Dashboard

| Widget | Status | Notes |
|---|---|---|
| Portfolio Value | Frontend only | Demo mode: `DEMO.portfolio.total_value`. Real mode: hardcoded `0`. Real backend exists and works (`GET /portfolio/`) but `refreshDashboard()` never calls it. |
| Day P&L / Total P&L | Frontend only | Same as above — hardcoded `0` outside demo mode, real endpoint unused. |
| Buying Power | Frontend only | Same pattern. |
| Equity Curve chart | Backend missing | Demo mode plots `DEMO.equity` (41 fake points). Real mode plots a single flat point `[100000]` — there is no equity/portfolio-history time-series endpoint anywhere in the API to plot even if the frontend were wired. |
| Open Positions table | Frontend only | `GET /portfolio/` (or `/positions/`) returns real position data server-side; frontend shows demo rows or "No positions", never calls it. |
| Active Strategies panel | Backend missing | No `/strategies` (or equivalent) router exists at all. `DEMO.strategies` is entirely invented; there is nothing real to wire to. |
| Risk Status / Kill Switch / Max Drawdown / Daily Loss | Placeholder | Hardcoded HTML (`NORMAL` / `DISARMED` / `0.0%`) — **identical values regardless of demo mode, and regardless of the actual risk_manager/kill_switch state on the server.** No risk-state API exists to expose the real values. This is a materially misleading indicator on a *trading* dashboard: it will say "NORMAL" and "DISARMED" even if the real kill switch has tripped. |
| AI Engine status / Decisions Today / Avg Confidence | Placeholder | Hardcoded (`ONLINE`, `6`, `82%`) unconditionally — not sourced from `/decisions/` (which is real) or any AI-engine status endpoint. |
| Market status / Market Time | Placeholder / Working | "OPEN" badge is hardcoded (no market-calendar logic). The clock next to it is a genuine local wall-clock (`setInterval`, correct but trivial — not fetched from a server). |

## 2. Trading

| Widget | Status | Notes |
|---|---|---|
| Watchlist | Backend missing | Demo-only data (`DEMO.watchlist`). No quotes/market-data router exists in the API to power a real watchlist. |
| Symbol panel (price/change header) | Backend missing | Driven entirely by the watchlist demo data; no live-quote endpoint to bind to. |
| BUY / SELL buttons | Not implemented | No `onclick`/event listener anywhere in `app.js` — confirmed by inspecting both the HTML and every `addEventListener` call. `POST /orders/` exists server-side, fully implemented (validates side/type/quantity, submits to the broker), and is completely unused. |
| Interactive chart | Placeholder | Literal text: "Interactive Chart (TradingView integration placeholder)". |
| Orders tab | Frontend only | `GET /orders/` is real and working; table only ever shows `DEMO.orders` or nothing. |
| Positions tab | Frontend only | Same pattern as Dashboard's Open Positions. |
| Closed tab | Backend missing + bug | Renders `DEMO.closed` **unconditionally, even with demo mode off** (the code never checks `demoMode` for this one table). There is also no "closed positions / realized P&L history" endpoint anywhere in the API — this data doesn't exist server-side to begin with. |
| Risk Panel (Max Drawdown, Daily Loss Limit, Consecutive Losses, Margin Used) | Placeholder | 100% static HTML, does not read `demoMode` at all, never changes. |
| AI Decisions panel | Frontend only + bug | Renders `DEMO.decisions.slice(0,4)` **unconditionally**, same bug as the Closed tab. `GET /decisions/` is real and returns genuine decision records but is never called here. |
| Orders / Positions / Closed tab switcher | Working | Pure client-side UI state (`.tab`/`.tab-content` class toggling) — this interaction itself works correctly; it's the *content* inside that's fake. |

## 3. AI Center

| Widget | Status | Notes |
|---|---|---|
| Current AI Recommendation (signal, symbol, strategy, confidence ring) | Backend missing | Demo mode uses `DEMO.ai`. Real mode falls back to a hardcoded "HOLD / no data" object. Even a correctly wired frontend would have nothing to call: no endpoint returns "the current top-confidence decision." |
| Analysis & Risk (reasoning, risk factors, target price, stop loss) | Backend missing | `GET /decisions/` (the one real, working decisions endpoint) does not return `reasoning`, `risk_factors`, `target_price`, or `stop_loss` fields at all — only `decision_id`, `timestamp`, `phase`, `symbol`, `price`, `strategy`, `confidence`, `outcome`, `realized_pnl`. This entire card's data model doesn't exist in the API contract. |
| Decision History table | Frontend only + bug | Renders `DEMO.decisions` **unconditionally regardless of demo mode** — identical bug pattern to Trading's AI Decisions panel and Closed tab. `GET /decisions/` is real, implemented, supports filtering/pagination, and is never called. |

## 4. Paper Trading

| Widget | Status | Notes |
|---|---|---|
| Session Status / Initial Capital / Current Value / Trades Executed | Frontend only | Real mode uses a hardcoded fallback object, never calls the real and working `GET /execution/paper/status`. |
| Start Session button | Working (with a contract bug) | Calls real `POST /execution/paper/start`. **Bug:** frontend sends `{symbols, capital: 100000}`; the backend's `PaperTradingStartRequest` model expects the field name `initial_capital`. FastAPI silently ignores the unrecognized `capital` field and falls back to its own default (100000.0) — so it happens to work today only because the default matches the hardcoded frontend value. Any UI that let a user pick a different capital amount would silently be ignored. |
| Pause button | Not implemented | Handler explicitly no-ops (`/* no pause state */`). No pause capability exists in `PaperTradingMode` on the backend either — this isn't just unwired, the capability doesn't exist. |
| Stop Session button | Working | Calls real `POST /execution/paper/stop`, correctly implemented end to end. |
| Session Configuration card | Placeholder | Hardcoded values ("AAPL, MSFT, GOOGL", "1.0s", "100%", "Paper Broker") — does not reflect whatever was actually configured on Start. |
| Live Activity log | Backend missing | Real mode's fallback object always has `trades: []`, so this branch is effectively dead in practice; even if reached, it renders the same six hardcoded demo log lines, not real trade events. No trade-event/activity feed is exposed over REST (the real `/ws/decisions` and `/ws/market` WebSockets exist but are never connected to from the frontend — see cross-cutting finding above). |

## 5. System Health

| Widget | Status | Notes |
|---|---|---|
| Service Status list (API/Database/Redis/Kafka/Workers) | Working | Calls real `GET /health/` outside demo mode; renders genuine backend health-check results. |
| Memory Usage / CPU Usage bars | Frontend only | `refreshHealth()` never touches these DOM elements at all — they permanently display the values baked into the HTML at page-load time ("128 MB / 4.0 GB (3.2%)", "8.5%"), in both demo and real mode. Real data is available server-side (`GET /diagnostics/memory`, `GET /diagnostics/system`) and is never called. |
| API Latency bar | Placeholder | Hardcoded "12ms", never updated by any code path. |
| Performance Metrics chart | Placeholder | Hardcoded text: "Metrics visualization requires Prometheus data." Real, working endpoints exist (`GET /metrics/prometheus`, `GET /metrics/snapshot`) and are entirely unused. |

## 6. Reports

| Widget | Status | Notes |
|---|---|---|
| Generated Reports list | Placeholder | A hardcoded array of 5 fake report entries with fixed dates (`2026-08-11/12`) — identical in demo and real mode; there is no `demoMode` branch at all. |
| Download button | Not implemented | Confirmed by grep: **no "report" endpoint exists anywhere in the API** (zero matches across every router file). The button generates a client-side `.txt` `Blob` whose literal content is: *"This is a sample report generated in demo mode. In production, this would contain actual data."* — this placeholder string ships unconditionally in production code today, regardless of demo mode. |

---

## Root-cause summary

Two patterns account for nearly everything above:

1. **A real, reasonably capable backend exists (portfolio, positions, orders, decisions, execution, health, diagnostics, metrics, audit, WebSocket) that the frontend almost never calls.** Outside System Health and (partially) Paper Trading, `app.js` was built against a `demoMode` flag and a hand-written `DEMO` object, and the "real" code path was mostly left as zeroed-out/hardcoded stand-ins rather than actually wired to the working endpoints.
2. **Three panels leak demo data even with Demo Mode switched off** (Trading's Closed tab and AI Decisions panel, AI Center's Decision History) — these read `DEMO.*` directly instead of checking `demoMode` like every other panel does. This is a real bug, not a design choice: a live operator with demo mode off would see fabricated trades and decisions presented as real.
3. Two features have **no backend at all**, not just an unwired frontend: Reports (no endpoint anywhere) and the Dashboard equity curve / Active Strategies (no time-series or strategy-registry endpoint).

---

## Prioritized Implementation Roadmap

**P0 — Correctness / safety (ship before any real trading use)**
1. Fix the three demo-data leaks (Trading Closed tab, Trading AI Decisions panel, AI Center Decision History) to respect `demoMode` — showing fabricated trades/decisions as real data is the single most dangerous defect found.
2. Wire Dashboard's Risk Status / Kill Switch / Max Drawdown / Daily Loss to real state. Requires: a small `/risk` (or extend `/status`) endpoint exposing the real `risk_manager`/`kill_switch` component state, then bind the frontend to it. A trading dashboard must not hardcode "NORMAL / DISARMED."
3. Fix the Paper Trading Start payload contract bug (`capital` → `initial_capital`) before any UI is added to let a user actually choose a capital amount.

**P1 — Wire existing, working backend to the frontend (highest value-per-effort)**
4. Dashboard: Portfolio Value, Day/Total P&L, Buying Power, Open Positions → call `GET /portfolio/`.
5. Trading: Orders tab → `GET /orders/`; Positions tab → `GET /portfolio/` or `/positions/`; BUY/SELL buttons → wire to `POST /orders/` (already fully implemented server-side, just needs a form/modal and click handlers).
6. AI Center: Decision History → `GET /decisions/` (real, filterable, paginated — just needs to be called).
7. Paper Trading: stat cards → `GET /execution/paper/status`; Session Configuration card → populate from the same response instead of hardcoding.
8. System Health: Memory/CPU/API Latency bars → `GET /diagnostics/memory` and `GET /diagnostics/system`; Performance Metrics chart → `GET /metrics/snapshot` or `/metrics/prometheus`.

**P2 — Genuine backend gaps (net-new work, not just wiring)**
9. Reports: design and build an actual report-generation endpoint (or explicitly descope the feature from the beta and say so in the UI, rather than shipping a fake download).
10. AI Center's "Current Recommendation" + reasoning/risk-factors/target/stop: either extend `DecisionRecord`/the `/decisions/` response to carry these fields (if the intelligence layer computes them internally already), or scope them out.
11. Dashboard: Active Strategies — needs a strategy-registry endpoint if strategy allocation/status is meant to be real; equity curve needs a portfolio-history time-series endpoint.
12. Trading: Watchlist / live quotes — needs a market-data/quotes endpoint; there is currently no such router.
13. Paper Trading: Pause — decide if this is a real requirement; if so it needs backend support in `PaperTradingMode`, not just a frontend handler.

**P3 — Nice-to-have / polish**
14. Replace the always-on "● Live" badge with a real WebSocket connection to `/ws/decisions` and `/ws/market` (both already implemented server-side and unused), or remove the "Live"/"Real-time" language until it's true.
15. Trading chart panel: replace the literal "TradingView integration placeholder" text with a real charting library once a quotes/OHLCV data source exists (depends on item 12).

---

*No code was changed as part of this audit — this is a read-only assessment per the request that produced it.*
