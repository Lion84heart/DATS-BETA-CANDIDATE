# RB-012: Health Verification

**Version:** 1.0
**Date:** 2026-08-08
**Platform:** DATS Beta v1.0
**Audience:** Operator, Admin

---

## 1. Purpose

Verify that all platform components (HTTP endpoints, authentication, WebSockets, paper trading, dashboard, Prometheus metrics) are operational after startup or suspected degradation.

## 2. Preconditions

| Item | Requirement | Verification |
|------|-------------|------------|
| System running | DATS process is active on port 8000 | `curl -s http://localhost:8000/health/` returns 200 |
| Network access | Can reach localhost:8000 from execution host | `nc -z localhost 8000` succeeds |
| Test credentials | Valid username/password for each RBAC role | Able to log in via `/auth/login` |
| WebSocket client | `websocat` or `wscat` installed, or Python with `websockets` | `which websocat` or `python -c "import websockets"` |
| `jq` installed | JSON parser for validation | `which jq` or `python -m json.tool` available |

## 3. Procedure

### Step 1: Verify Basic HTTP Endpoints
```bash
curl -s http://localhost:8000/health/ | python -m json.tool
curl -s http://localhost:8000/status/ | python -m json.tool
curl -s http://localhost:8000/system/state | python -m json.tool
curl -s http://localhost:8000/system/version | python -m json.tool
```
**Expected outcome:**
- `/health/` → `{"status": "ok"}`
- `/status/` → `{"status": "ok"}`
- `/system/state` → `{"status": "HEALTHY"}`
- `/system/version` → `{"version": "1.0.0-beta", "release": "Alpha Release Candidate", "build_date": "2026-08-08"}`

### Step 2: Verify Diagnostics Endpoints
```bash
curl -s http://localhost:8000/diagnostics/runtime | python -m json.tool
curl -s http://localhost:8000/diagnostics/performance | python -m json.tool
curl -s http://localhost:8000/diagnostics/dependencies | python -m json.tool
curl -s http://localhost:8000/diagnostics/config | python -m json.tool
```
**Expected outcome:**
- `/diagnostics/runtime` → JSON with `platform`, `python_version`, `timestamp`
- `/diagnostics/performance` → `{"cpu_percent": 0.0, "memory_mb": 163.6, "memory_percent": 2.0}`
- `/diagnostics/dependencies` → `{"dependencies": [...], "count": N}`
- `/diagnostics/config` → `{"config_source": "...", "settings_loaded": true}`

### Step 3: Verify Config Validation
```bash
curl -s http://localhost:8000/config/validate | python -m json.tool
```
**Expected outcome:** `{"valid": true, "warnings": [], "errors": []}`

### Step 4: Verify Authentication (All RBAC Roles)

**4a. Login as VIEWER:**
```bash
VIEWER_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=viewer&password=$VIEWER_PASSWORD" | jq -r '.access_token')
echo "VIEWER token: ${VIEWER_TOKEN:0:20}..."
curl -s http://localhost:8000/audit/history \
  -H "Authorization: Bearer $VIEWER_TOKEN" | python -m json.tool | head -n 5
```
**Expected outcome:** Token received. VIEWER can access read-only endpoints.

**4b. Login as ANALYST:**
```bash
ANALYST_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=analyst&password=$ANALYST_PASSWORD" | jq -r '.access_token')
echo "ANALYST token: ${ANALYST_TOKEN:0:20}..."
```
**Expected outcome:** Token received. ANALYST can access analytics endpoints.

**4c. Login as OPERATOR:**
```bash
OPERATOR_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=operator&password=$OPERATOR_PASSWORD" | jq -r '.access_token')
echo "OPERATOR token: ${OPERATOR_TOKEN:0:20}..."
curl -s http://localhost:8000/audit/history \
  -H "Authorization: Bearer $OPERATOR_TOKEN" | python -m json.tool | head -n 5
```
**Expected outcome:** Token received with `{"role": "OPERATOR"}`. OPERATOR can access operational endpoints.

**4d. Login as ADMIN:**
```bash
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=$ADMIN_PASSWORD" | jq -r '.access_token')
echo "ADMIN token: ${ADMIN_TOKEN:0:20}..."
curl -s http://localhost:8000/audit/history \
  -H "Authorization: Bearer $ADMIN_TOKEN" | python -m json.tool | head -n 5
```
**Expected outcome:** Token received with `{"role": "ADMIN"}`. ADMIN can access all endpoints including shutdown.

**4e. Verify unauthorized access is blocked:**
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/system/shutdown -X POST
```
**Expected outcome:** HTTP `403` Forbidden (no token).

### Step 5: Verify WebSocket Endpoints

**5a. WebSocket — Decisions:**
```bash
# Using websocat (if installed)
timeout 5 websocat ws://localhost:8000/ws/decisions 2>/dev/null || echo "websocat not available"
```
**Alternative using Python:**
```bash
python3 -c "
import asyncio, websockets
async def test():
    async with websockets.connect('ws://localhost:8000/ws/decisions') as ws:
        print('Connected to /ws/decisions')
        # Wait for initial message or close after 2s
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=2)
            print('Received:', msg[:100])
        except asyncio.TimeoutError:
            print('No immediate message (OK for subscription socket)')
asyncio.run(test())
"
```
**Expected outcome:** Connection established successfully.

**5b. WebSocket — Market:**
```bash
python3 -c "
import asyncio, websockets
async def test():
    async with websockets.connect('ws://localhost:8000/ws/market') as ws:
        print('Connected to /ws/market')
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=2)
            print('Received:', msg[:100])
        except asyncio.TimeoutError:
            print('No immediate message (OK)')
asyncio.run(test())
"
```
**Expected outcome:** Connection established successfully.

**5c. WebSocket — System:**
```bash
python3 -c "
import asyncio, websockets
async def test():
    async with websockets.connect('ws://localhost:8000/ws/system') as ws:
        print('Connected to /ws/system')
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=2)
            print('Received:', msg[:100])
        except asyncio.TimeoutError:
            print('No immediate message (OK)')
asyncio.run(test())
"
```
**Expected outcome:** Connection established successfully.

### Step 6: Verify Prometheus Metrics
```bash
curl -s http://localhost:8000/metrics/prometheus | head -n 20
```
**Expected outcome:** Valid Prometheus text format starting with `# HELP` or metric lines such as `http_requests_total`, `process_resident_memory_bytes`, etc.

### Step 7: Verify Audit History
```bash
curl -s http://localhost:8000/audit/history \
  -H "Authorization: Bearer $OPERATOR_TOKEN" | python -m json.tool | head -n 10
```
**Expected outcome:** JSON with `{"entries": [...], "total": N}` where `N >= 0`.

### Step 8: Run Full Test Suite
```bash
cd /opt/DATS-BETA-CANDIDATE
source .venv/bin/activate
pytest tests/ -q --tb=short
```
**Expected outcome:** `183 passed` with `0 failed`, `0 error`.

### Step 9: Automated Health Verification Script

Save and execute the following script for repeatable health checks:

```bash
cat > /opt/DATS-BETA-CANDIDATE/scripts/health_check.sh << 'EOF'
#!/bin/bash
# DATS — Automated Health Verification Script
# Version: 1.0
# Date: 2026-08-08

BASE_URL="http://localhost:8000"
FAILED=0

check_endpoint() {
    local path="$1"
    local expected="$2"
    local response
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}${path}")
    response=$(curl -s "${BASE_URL}${path}")
    if [ "$code" -eq 200 ] && echo "$response" | grep -q "$expected"; then
        echo "[PASS] ${path} => ${expected}"
    else
        echo "[FAIL] ${path} => expected ${expected}, got HTTP ${code}: ${response}"
        FAILED=$((FAILED + 1))
    fi
}

echo "=== DATS Health Check ==="
echo "Timestamp: $(date -Iseconds)"
echo ""

check_endpoint "/health/" '"status": "ok"'
check_endpoint "/status/" '"status": "ok"'
check_endpoint "/system/state" '"status": "HEALTHY"'
check_endpoint "/system/version" '"version": "1.0.0-beta"'
check_endpoint "/diagnostics/runtime" '"python_version"'
check_endpoint "/diagnostics/performance" '"memory_mb"'
check_endpoint "/diagnostics/dependencies" '"dependencies"'
check_endpoint "/diagnostics/config" '"settings_loaded": true'
check_endpoint "/config/validate" '"valid": true'

# Prometheus metrics check (no JSON, just text)
metrics=$(curl -s "${BASE_URL}/metrics/prometheus")
if echo "$metrics" | grep -q "http_requests_total\|process_"; then
    echo "[PASS] /metrics/prometheus => Prometheus format valid"
else
    echo "[FAIL] /metrics/prometheus => Invalid or empty response"
    FAILED=$((FAILED + 1))
fi

echo ""
if [ $FAILED -eq 0 ]; then
    echo "=== ALL CHECKS PASSED ==="
    exit 0
else
    echo "=== ${FAILED} CHECK(S) FAILED ==="
    exit 1
fi
EOF
chmod +x /opt/DATS-BETA-CANDIDATE/scripts/health_check.sh
```

**Execute the script:**
```bash
/opt/DATS-BETA-CANDIDATE/scripts/health_check.sh
```
**Expected outcome:** All checks show `[PASS]`, final line is `=== ALL CHECKS PASSED ===`.

## 4. Validation Checks

| # | Check | Expected Result | Method |
|---|-------|-----------------|--------|
| 1 | Health endpoint | `{"status": "ok"}` | `curl -s http://localhost:8000/health/` |
| 2 | Status endpoint | `{"status": "ok"}` | `curl -s http://localhost:8000/status/` |
| 3 | System state | `{"status": "HEALTHY"}` | `curl -s http://localhost:8000/system/state` |
| 4 | System version | `{"version": "1.0.0-beta"}` | `curl -s http://localhost:8000/system/version` |
| 5 | Diagnostics runtime | Contains `platform`, `python_version`, `timestamp` | `curl -s http://localhost:8000/diagnostics/runtime` |
| 6 | Diagnostics performance | `memory_mb` < 256, `memory_percent` < 5 | `curl -s http://localhost:8000/diagnostics/performance` |
| 7 | Config validation | `{"valid": true}` | `curl -s http://localhost:8000/config/validate` |
| 8 | Auth login (all roles) | Valid JWT returned for VIEWER, ANALYST, OPERATOR, ADMIN | `POST /auth/login` for each role |
| 9 | Unauthorized access blocked | HTTP 403 for protected endpoints without token | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/system/shutdown -X POST` |
| 10 | WebSocket connections | Connection established on all 3 endpoints | Python `websockets` or `websocat` |
| 11 | Prometheus metrics | Valid Prometheus text output | `curl -s http://localhost:8000/metrics/prometheus` |
| 12 | Audit history | JSON with `entries` and `total` | `GET /audit/history` with valid token |
| 13 | Test suite | `183 passed` | `pytest tests/ -q` |
| 14 | Automated script | `=== ALL CHECKS PASSED ===` | `/opt/DATS-BETA-CANDIDATE/scripts/health_check.sh` |

## 5. Recovery Procedures

| Scenario | Symptom | Recovery Steps |
|----------|---------|----------------|
| Health endpoint fails | `/health/` returns non-200 | Restart service: `sudo systemctl restart DATS-BETA-CANDIDATE`; wait 10s; re-run health check |
| System state not HEALTHY | `/system/state` returns non-HEALTHY | Check logs: `tail -n 50 /opt/DATS-BETA-CANDIDATE/logs/dats.log`; run RB-010 diagnostics |
| Auth login fails | `/auth/login` returns 401/403 | Verify credentials; check if auth service is running; restart if needed |
| WebSocket connection refused | `Connection refused` or timeout on WS | Verify server is running; check firewall rules; restart DATS |
| Prometheus metrics empty | `/metrics/prometheus` returns empty | Restart DATS metrics exporter; verify Prometheus middleware is loaded |
| Diagnostics endpoint fails | `/diagnostics/*` returns 500 | Clear Python cache: `find /opt/DATS-BETA-CANDIDATE -name "*.pyc" -delete`; restart DATS |
| Config validation fails | `/config/validate` returns `valid: false` | Review `warnings` and `errors` in response; correct configuration file; restart DATS |
| Multiple checks fail | > 3 checks fail in automated script | Follow [RB-010: Failure Recovery](RB-010-FAILURE-RECOVERY.md) |

## 6. Related Runbooks

- [RB-010: Failure Recovery](RB-010-FAILURE-RECOVERY.md) — When health checks fail
- [RB-011: Incident Response](RB-011-INCIDENT-RESPONSE.md) — When degradation is part of a broader incident
- [RB-013: Performance Verification](RB-013-PERFORMANCE-VERIFICATION.md) — When health is OK but performance is degraded

## 7. Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-08 | Initial version |
