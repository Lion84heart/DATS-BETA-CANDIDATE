# RB-004: Daily Operator Workflow

**Version:** 1.0
**Date:** 2026-08-08
**Platform:** DATS Beta v1.0
**Audience:** Operator

---

## 1. Purpose

Execute the standard daily operational workflow on the DATS Beta v1.0 trading platform, from authentication through paper trading, order submission, monitoring, data export, and logout.

---

## 2. Preconditions

| Item | Requirement | Verification |
|------|-------------|------------|
| System state | Platform running and healthy | `curl -s http://localhost:8000/health/` returns `status: "ok"` |
| Operator credentials | Valid OPERATOR role username and password | Credentials stored in secure vault |
| Market hours | Paper trading engine available | Check `/system/capabilities` for trading capability |
| Network | Stable connection to localhost:8000 | `ping -c 3 localhost` |
| Data directory | Writable location for exports | `test -w /opt/DATS-BETA-CANDIDATE/exports/` |

---

## 3. Procedure

### Step 1: Authenticate as Operator

```bash
AUTH_RESPONSE=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "operator", "password": "<OPERATOR_PASSWORD>"}')
OPERATOR_TOKEN=$(echo "$AUTH_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
OPERATOR_ROLE=$(echo "$AUTH_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['role'])")
echo "Role: $OPERATOR_ROLE"
```

**Expected outcome:**
```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "role": "OPERATOR"
}
```
`OPERATOR_ROLE` equals `"OPERATOR"`.

### Step 2: Verify Authentication

```bash
curl -s http://localhost:8000/auth/sessions \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  | python3 -m json.tool
```

**Expected outcome:**
```json
[
    {
        "id": "<session-id>",
        "role": "OPERATOR",
        "created_at": "2026-08-08T..."
    }
]
```

### Step 3: Health Check

```bash
curl -s http://localhost:8000/health/ \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "status": "ok",
    "version": "1.0.0-beta"
}
```

### Step 4: System State Check

```bash
curl -s http://localhost:8000/system/state \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "status": "HEALTHY"
}
```

### Step 5: System Capabilities Check

```bash
curl -s http://localhost:8000/system/capabilities \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "capabilities_count": 32,
    "readiness_percentage": 100.0,
    "validated": true
}
```

### Step 6: Diagnostics - Runtime Check

```bash
curl -s http://localhost:8000/diagnostics/runtime \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  | python3 -m json.tool
```

**Expected outcome:** JSON response containing `platform`, `python_version`, and `timestamp` fields.

### Step 7: Diagnostics - Performance Check

```bash
curl -s http://localhost:8000/diagnostics/performance \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "cpu_percent": 0.0,
    "memory_mb": <value>,
    "memory_percent": <value>
}
```
`memory_percent` should be < 80%.

### Step 8: Validate Configuration

```bash
curl -s http://localhost:8000/config/validate \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "valid": true,
    "warnings": [],
    "errors": []
}
```

### Step 9: Start Paper Trading

```bash
curl -s -X POST http://localhost:8000/trading/paper/start \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mode": "paper", "initial_balance": 100000.00}' \
  | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "status": "started",
    "mode": "paper",
    "initial_balance": 100000.00
}
```

### Step 10: Submit a Paper Order

```bash
curl -s -X POST http://localhost:8000/orders \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "side": "BUY",
    "quantity": 100,
    "order_type": "LIMIT",
    "price": 175.50,
    "time_in_force": "DAY"
  }' \
  | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "order_id": "<uuid>",
    "symbol": "AAPL",
    "side": "BUY",
    "quantity": 100,
    "status": "PENDING",
    "created_at": "2026-08-08T..."
}
```

### Step 11: Monitor Order Status

```bash
ORDER_ID="<order-id-from-step-10>"
curl -s "http://localhost:8000/orders/${ORDER_ID}" \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  | python3 -m json.tool
```

**Expected outcome:** Order status transitions to `FILLED` or `PARTIALLY_FILLED` within paper trading simulation.

### Step 12: List All Positions

```bash
curl -s http://localhost:8000/positions \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  | python3 -m json.tool
```

**Expected outcome:** Array containing position object:
```json
[
    {
        "symbol": "AAPL",
        "quantity": 100,
        "avg_entry_price": 175.50,
        "unrealized_pnl": <value>
    }
]
```

### Step 13: Review Trading Decisions / AI Signals

```bash
curl -s http://localhost:8000/decisions \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  | python3 -m json.tool
```

**Expected outcome:** Array of decision records with timestamps, signals, and confidence scores.

### Step 14: Export Session Data

```bash
mkdir -p /opt/DATS-BETA-CANDIDATE/exports
curl -s "http://localhost:8000/exports/session?format=csv" \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -o /opt/DATS-BETA-CANDIDATE/exports/session_$(date +%Y%m%d_%H%M%S).csv
ls -la /opt/DATS-BETA-CANDIDATE/exports/
```

**Expected outcome:** CSV file created with nonzero size in `/opt/DATS-BETA-CANDIDATE/exports/`.

### Step 15: Stop Paper Trading

```bash
curl -s -X POST http://localhost:8000/trading/paper/stop \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "status": "stopped",
    "mode": "paper",
    "final_balance": <value>,
    "realized_pnl": <value>
}
```

### Step 16: Logout

```bash
curl -s -X POST http://localhost:8000/auth/logout \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "message": "Logged out successfully"
}
```

### Step 17: Verify Session Termination

```bash
curl -s http://localhost:8000/auth/sessions \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  | python3 -m json.tool
```

**Expected outcome:**
```json
[]
```
Or `401 Unauthorized` if token is fully invalidated.

---

## 4. Validation Checks

| # | Check | Expected Result | Method |
|---|-------|-----------------|--------|
| 1 | Login success | HTTP 200, `role: "OPERATOR"` | Parse `AUTH_RESPONSE` |
| 2 | Session active | Sessions array contains OPERATOR entry | `GET /auth/sessions` |
| 3 | Health OK | `status: "ok"` | `GET /health/` |
| 4 | System HEALTHY | `status: "HEALTHY"` | `GET /system/state` |
| 5 | Capabilities ready | `readiness_percentage: 100.0` | `GET /system/capabilities` |
| 6 | Config valid | `valid: true, errors: []` | `GET /config/validate` |
| 7 | Paper trading started | `status: "started"` | `POST /trading/paper/start` |
| 8 | Order accepted | Order ID returned, status `PENDING` | `POST /orders` |
| 9 | Position created | `AAPL` position with quantity 100 | `GET /positions` |
| 10 | Data exported | File exists and size > 0 bytes | `ls -la exports/` |
| 11 | Paper trading stopped | `status: "stopped"` | `POST /trading/paper/stop` |
| 12 | Logout success | `message: "Logged out successfully"` | `POST /auth/logout` |

---

## 5. Recovery Procedures

| Scenario | Symptom | Recovery Steps |
|----------|---------|----------------|
| Auth failure (401) | `{"detail": "Invalid credentials"}` | 1. Verify username and password 2. Check account is not locked 3. Re-authenticate with correct credentials 4. If admin access available, reset password via admin endpoint |
| Auth failure (403) | `{"detail": "Not enough permissions"}` | 1. Verify `OPERATOR_TOKEN` not expired: check token timestamp 2. Re-authenticate to obtain fresh token 3. Ensure user has OPERATOR role (not VIEWER) |
| Paper trading already running | `{"detail": "Paper trading already active"}` | 1. Query current status: `GET /trading/paper/status` 2. If session is stale from previous day, stop and restart: `POST /trading/paper/stop` then `POST /trading/paper/start` |
| Order rejected | `{"detail": "Order rejected: <reason>"}` | 1. Check symbol validity and market data availability 2. Verify `price` is within allowed bounds 3. Check `quantity` is a positive integer 4. Review `time_in_force` is valid (`DAY`, `GTC`, `IOC`) 5. Resubmit with corrected parameters |
| Insufficient paper balance | `{"detail": "Insufficient balance"}` | 1. Check current paper balance: `GET /trading/paper/account` 2. Reduce order quantity or price 3. Restart paper trading with higher `initial_balance` if needed |
| Export fails | Empty file or 500 error | 1. Verify `exports/` directory exists and is writable 2. Check disk space: `df -h` 3. Retry export with different format: `?format=json` 4. If persistent, copy data via API manually |
| Performance alert | `memory_percent` > 80% | 1. Document current memory usage 2. Reduce concurrent operations 3. Check for memory leaks: compare `GET /diagnostics/performance` over time 4. Restart platform if memory continues climbing |
| Token expired mid-session | `401 Unauthorized` on any endpoint | 1. Re-authenticate using Step 1 2. Update `OPERATOR_TOKEN` environment variable 3. Resume workflow from interrupted step |
| Session shows no role | Empty or incorrect role in `/auth/sessions` | 1. Logout fully: `POST /auth/logout` 2. Clear `OPERATOR_TOKEN` 3. Re-authenticate from Step 1 |

---

## 6. Related Runbooks

- [RB-001: Initial Deployment](RB-001-INITIAL-DEPLOYMENT.md)
- [RB-002: System Startup](RB-002-SYSTEM-STARTUP.md)
- [RB-003: System Shutdown](RB-003-SYSTEM-SHUTDOWN.md)
- [RB-009: Upgrade Procedure](RB-009-UPGRADE-PROCEDURE.md)

---

## 7. Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-08 | Initial version |
