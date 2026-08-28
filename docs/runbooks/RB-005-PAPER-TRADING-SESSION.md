# RB-005: Paper Trading Session

**Version:** 1.0
**Date:** 2026-08-08
**Platform:** DATS Beta v1.0
**Audience:** OPERATOR, ANALYST

---

## 1. Purpose

Execute a controlled paper trading session to validate order flow, position tracking, and PnL calculation without risking live capital.

## 2. Preconditions

| Item | Requirement | Verification |
|------|-------------|------------|
| Platform Running | FastAPI server listening on port 8000 | `curl -s http://localhost:8000/health` returns HTTP 200 |
| Operator Authenticated | Valid JWT access token with OPERATOR role | POST /auth/login returns `role: OPERATOR` |
| Paper Trading Inactive | No active paper trading session running | GET /execution/paper/status returns `status: stopped` or HTTP 404 |
| Cash Available | Paper account has cash balance > $100 | GET /portfolio/summary returns `cash >= 100` |
| Network Access | localhost:8000 reachable from operator workstation | `ping -c 1 localhost` succeeds |

## 3. Procedure

### Step 1: Authenticate and Obtain JWT Token

```bash
curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "operator", "password": "operator_pass"}' | jq .
```

**Expected outcome:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "role": "OPERATOR"
}
```

Store the token in an environment variable:
```bash
export TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### Step 2: Verify Paper Trading Is Not Already Active

```bash
curl -s -X GET http://localhost:8000/execution/paper/status \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected outcome:**
```json
{
  "status": "stopped",
  "mode": "paper",
  "broker": "PaperBroker"
}
```

If the endpoint returns HTTP 404, paper trading is not active — proceed.

### Step 3: Start Paper Trading Session

```bash
curl -s -X POST http://localhost:8000/execution/paper/start \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" | jq .
```

**Expected outcome:**
```json
{
  "status": "running",
  "mode": "paper",
  "broker": "PaperBroker"
}
```

### Step 4: Verify Portfolio Summary Before Trading

```bash
curl -s -X GET http://localhost:8000/portfolio/summary \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected outcome:**
```json
{
  "total_value": 100000,
  "cash": 100000,
  "positions_value": 0
}
```

### Step 5: Submit a Single Market Buy Order

```bash
curl -s -X POST http://localhost:8000/orders/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "side": "buy",
    "order_type": "market",
    "quantity": 10
  }' | jq .
```

**Expected outcome:**
```json
{
  "id": "ORD-20260808-001",
  "symbol": "AAPL",
  "side": "buy",
  "status": "filled",
  "quantity": 10,
  "filled_quantity": 10,
  "avg_fill_price": 185.32
}
```

### Step 6: Submit a Batch of Orders

```bash
curl -s -X POST http://localhost:8000/orders/batch \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '[
    {"symbol": "MSFT", "side": "buy", "order_type": "market", "quantity": 5},
    {"symbol": "GOOGL", "side": "buy", "order_type": "market", "quantity": 2},
    {"symbol": "TSLA", "side": "sell", "order_type": "market", "quantity": 3}
  ]' | jq .
```

**Expected outcome:**
```json
[
  {"id": "ORD-20260808-002", "status": "filled", "symbol": "MSFT"},
  {"id": "ORD-20260808-003", "status": "filled", "symbol": "GOOGL"},
  {"id": "ORD-20260808-004", "status": "filled", "symbol": "TSLA"}
]
```

### Step 7: Retrieve Order History

```bash
curl -s -X GET "http://localhost:8000/orders/history?limit=10" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected outcome:**
```json
{
  "orders": [
    {"id": "ORD-20260808-004", "symbol": "TSLA", "status": "filled"},
    {"id": "ORD-20260808-003", "symbol": "GOOGL", "status": "filled"},
    {"id": "ORD-20260808-002", "symbol": "MSFT", "status": "filled"},
    {"id": "ORD-20260808-001", "symbol": "AAPL", "status": "filled"}
  ],
  "total": 4
}
```

### Step 8: Verify Positions

```bash
curl -s -X GET http://localhost:8000/positions/ \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected outcome:**
```json
{
  "positions": [
    {"symbol": "AAPL", "quantity": 10, "avg_cost": 185.32},
    {"symbol": "MSFT", "quantity": 5, "avg_cost": 420.15},
    {"symbol": "GOOGL", "quantity": 2, "avg_cost": 175.80}
  ]
}
```

TSLA sell order should reduce or close an existing position. If no prior TSLA position existed, quantity may be negative (short) or the order may have been rejected based on configuration.

### Step 9: Check Portfolio Summary After Fills

```bash
curl -s -X GET http://localhost:8000/portfolio/summary \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected outcome:**
```json
{
  "total_value": 99952.45,
  "cash": 91711.28,
  "positions_value": 8241.17
}
```

Cash should be reduced by the cost of fills plus commissions and slippage (30 bps slippage + 20 bps price impact). Positions value should reflect filled quantities at simulated fill prices.

### Step 10: Stop Paper Trading Session

```bash
curl -s -X POST http://localhost:8000/execution/paper/stop \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" | jq .
```

**Expected outcome:**
```json
{
  "status": "stopped",
  "mode": "paper"
}
```

### Step 11: Confirm Session Stopped

```bash
curl -s -X GET http://localhost:8000/execution/paper/status \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Expected outcome:**
```json
{
  "status": "stopped",
  "mode": "paper",
  "broker": "PaperBroker"
}
```

## 4. Validation Checks

| # | Check | Expected Result | Method |
|---|-------|-----------------|--------|
| 1 | Login successful | HTTP 200, `role: OPERATOR` | `curl POST /auth/login` |
| 2 | Paper trading starts cleanly | `status: running`, no error | `curl POST /execution/paper/start` |
| 3 | Single order accepted | HTTP 200, `status: filled`, valid `id` | `curl POST /orders/` |
| 4 | Batch orders accepted | HTTP 200, all items `status: filled` | `curl POST /orders/batch` |
| 5 | Order history reflects trades | `total >= 4`, order IDs match | `curl GET /orders/history?limit=10` |
| 6 | Positions updated | Symbols present with correct quantities | `curl GET /positions/` |
| 7 | Portfolio summary updated | `cash < 100000`, `positions_value > 0` | `curl GET /portfolio/summary` |
| 8 | PnL calculated | `total_value` computed from cash + positions | Verify `total_value == cash + positions_value` |
| 9 | Paper trading stops cleanly | `status: stopped` | `curl POST /execution/paper/stop` |
| 10 | No stale session | Status endpoint returns `stopped` | `curl GET /execution/paper/status` |

## 5. Recovery Procedures

| Scenario | Symptom | Recovery Steps |
|----------|---------|----------------|
| Paper trading already running | Step 3 returns `status: running` | 1. Stop session: `POST /execution/paper/stop`<br>2. Wait 3 seconds<br>3. Restart: `POST /execution/paper/start` |
| Order rejected | Step 5 returns `status: rejected` | 1. Check rejection reason in response<br>2. Verify `cash >= order_value`<br>3. Verify `symbol` exists in allowed universe<br>4. Reduce `quantity` and retry |
| Batch order partially filled | Step 6 returns mixed `status` | 1. Note failed order IDs<br>2. Retry failed items individually<br>3. Check `GET /positions/` for partial fills |
| Stale position data | Step 8 shows stale `avg_cost` | 1. Restart paper trading: `POST /execution/paper/stop` then `POST /execution/paper/start`<br>2. If stale data persists, restart FastAPI server |
| Paper trading start fails | Step 3 returns HTTP 500 or error | 1. Check FastAPI logs: `tail -n 50 logs/dats.log`<br>2. Verify `TRADING_PAPER_TRADING=true` in `.env`<br>3. Restart server: `uvicorn main:app --reload` |
| Portfolio summary mismatch | Step 9 values do not add up | 1. Re-run `GET /portfolio/summary`<br>2. Check `GET /positions/` for phantom entries<br>3. Clear positions cache via admin endpoint if available |
| Session does not stop | Step 10 returns `status: running` | 1. Retry `POST /execution/paper/stop`<br>2. Check logs for lock contention<br>3. Force restart: kill FastAPI process, restart server<br>4. Verify no open orders: `GET /orders/history?status=open` |

## 6. Related Runbooks

- [RB-006: Decision Review Workflow](RB-006-DECISION-REVIEW-WORKFLOW.md)
- [RB-007: Backup Procedure](RB-007-BACKUP-PROCEDURE.md)
- [RB-008: Restore Procedure](RB-008-RESTORE-PROCEDURE.md)

## 7. Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-08 | Initial version |
