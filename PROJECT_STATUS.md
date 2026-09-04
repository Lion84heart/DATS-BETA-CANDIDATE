# DATS Beta — Project Status

**Last updated:** 2026-09-04 (Sprint 2 complete)

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

## Known gaps (not yet done, tracked from the audit)

- Trading page BUY/SELL buttons not wired (Paper Trading page covers manual trading for now).
- No live market-data/watchlist quotes (only the simulated paper-trading feed).
- No realized-P&L "closed positions" history distinct from the paper trading order history.
- Reports page has no backend.
- Memory/CPU/API Latency real host metrics (needs `psutil`).
- "● Live" badge and the two real WebSocket endpoints (`/ws/decisions`, `/ws/market`) exist server-side but nothing in the frontend connects to them yet — all updates are still 5-second polling.
- AI Center's Current Recommendation has no `target_price`/`stop_loss`/`signal` (action) fields anywhere in the backend's decision data model — shown honestly as N/A, not fabricated.
- Paper Trading Pause has no backend capability (button exists, does nothing).

## Sprint history

| Sprint | Focus | Report |
|---|---|---|
| — | Authentication fix (stale asset caching), initial CTO functional audit | [CTO-FUNCTIONAL-AUDIT-REPORT.md](docs/CTO-FUNCTIONAL-AUDIT-REPORT.md) |
| 1 | Truthfulness/production-safety pass — removed demo-data leaks, wired Dashboard/Trading/Health to real endpoints, fixed the Risk Status hardcode | [SPRINT-1-COMPLETION-REPORT.md](docs/SPRINT-1-COMPLETION-REPORT.md) |
| 2 | Paper Trading engine — real buy/sell, live positions, real-time P&L, closing positions, trade history | [SPRINT-2-COMPLETION-REPORT.md](docs/SPRINT-2-COMPLETION-REPORT.md) |
