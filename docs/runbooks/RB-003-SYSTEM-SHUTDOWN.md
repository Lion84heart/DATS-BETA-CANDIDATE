# RB-003: System Shutdown

**Version:** 1.0
**Date:** 2026-08-08
**Platform:** DATS Beta v1.0
**Audience:** Admin / Operator

---

## 1. Purpose

Gracefully shut down the DATS Beta v1.0 trading platform, ensuring all in-flight operations complete and data consistency is maintained.

---

## 2. Preconditions

| Item | Requirement | Verification |
|------|-------------|------------|
| System state | Platform running and responsive | `curl -s http://localhost:8000/health/` returns `status: "ok"` |
| Authentication | Admin role token available (for API shutdown) | Have valid `ACCESS_TOKEN` from prior login |
| Open orders | No live market orders in flight (if applicable) | Check trading dashboard or `/orders` endpoint |
| Backups | Data persisted or backed up if required by SLA | Verify database file timestamp: `ls -la dats.db` |
| Permissions | User has permission to terminate process | `whoami` and `sudo -l` (for kill procedures) |

---

## 3. Procedure

### Step 1: Verify System is Running

```bash
curl -s http://localhost:8000/health/ | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "status": "ok",
    "version": "1.0.0-beta"
}
```

### Step 2: Authenticate as ADMIN

```bash
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "<ADMIN_PASSWORD>"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
echo "Token obtained: ${ADMIN_TOKEN:0:20}..."
```

**Expected outcome:** `ADMIN_TOKEN` environment variable populated with JWT. No error output.

### Step 3: Verify Admin Role

```bash
curl -s http://localhost:8000/auth/sessions \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  | python3 -m json.tool
```

**Expected outcome:** Response includes `"role": "ADMIN"`.

### Step 4: Initiate Graceful Shutdown via API

```bash
curl -s -X POST http://localhost:8000/system/shutdown \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "message": "System shutdown initiated"
}
```

### Step 5: Wait for Shutdown to Complete

```bash
echo "Waiting for shutdown (max 30 seconds)..."
for i in {1..30}; do
  if ! curl -s http://localhost:8000/health/ >/dev/null 2>&1; then
    echo "Shutdown complete after ${i} seconds"
    break
  fi
  sleep 1
done
```

**Expected outcome:** Loop exits within 10-15 seconds with message `Shutdown complete after N seconds`.

### Step 6: Verify Process Termination

**Docker:**
```bash
docker ps --filter name=DATS-BETA-CANDIDATE
```

**Expected outcome:** No running container matching `DATS-BETA-CANDIDATE`.

**Local:**
```bash
ps aux | grep uvicorn | grep -v grep
```

**Expected outcome:** No Uvicorn processes found.

### Step 7: Verify Port Released

```bash
ss -tlnp | grep 8000 || echo "Port 8000 is free"
```

**Expected outcome:** Output: `Port 8000 is free`.

### Step 8: Verify Clean Exit in Logs

**Docker:**
```bash
docker logs DATS-BETA-CANDIDATE 2>&1 | tail -20
```

**Local:**
```bash
tail -n 20 dats.log
```

**Expected outcome:** Log contains orderly shutdown messages. No uncaught exceptions.

### Step 9: Verify Logout (Post-Shutdown Cleanup)

If the system is restarted later, any stale session state should be validated. After restart:
```bash
curl -s http://localhost:8000/auth/sessions
```

**Expected outcome:** Empty array `[]` or new sessions only (sessions do not persist across restarts).

### Step 10A: Docker Container Cleanup (Optional)

```bash
docker stop DATS-BETA-CANDIDATE 2>/dev/null
docker rm DATS-BETA-CANDIDATE 2>/dev/null
echo "Container removed"
```

**Expected outcome:** Container stopped and removed if graceful API shutdown did not already do so.

### Step 10B: Local Process Cleanup (if still running)

```bash
if [ -f dats.pid ]; then
  kill $(cat dats.pid) 2>/dev/null
  rm -f dats.pid
  echo "Process terminated via PID file"
fi
```

**Expected outcome:** Process killed using stored PID. PID file removed.

---

## Emergency Shutdown Procedure (Use when API is Unresponsive)

### Emergency Step 1: Identify Process

```bash
lsof -i :8000
```

**Expected outcome:** PID of process binding port 8000.

### Emergency Step 2: Send SIGTERM

```bash
kill -15 <PID>
sleep 5
```

**Expected outcome:** Process terminates gracefully.

### Emergency Step 3: Send SIGKILL (if SIGTERM fails)

```bash
kill -9 <PID>
```

**Expected outcome:** Process forcefully terminated immediately.

### Emergency Step 4: Verify Termination

```bash
lsof -i :8000 || echo "Port is free"
```

**Expected outcome:** `Port is free`.

---

## 4. Validation Checks

| # | Check | Expected Result | Method |
|---|-------|-----------------|--------|
| 1 | API unresponsive | `curl` connection refused | `curl -s http://localhost:8000/health/` returns exit code 7 |
| 2 | Port released | Nothing on TCP 8000 | `ss -tlnp \| grep 8000` returns empty |
| 3 | Process gone | No Uvicorn process | `ps aux \| grep uvicorn \| grep -v grep` returns empty |
| 4 | Log clean exit | No ERROR during shutdown | `tail -n 30 dats.log \| grep -i error` returns empty |
| 5 | Database intact | SQLite file not corrupted | `sqlite3 dats.db "PRAGMA integrity_check;"` returns `ok` |
| 6 | No stale sessions | Sessions list empty after restart | `curl -s http://localhost:8000/auth/sessions` returns `[]` |

---

## 5. Recovery Procedures

| Scenario | Symptom | Recovery Steps |
|----------|---------|----------------|
| API shutdown returns 403 | `{"detail": "Not enough permissions"}` | 1. Verify token belongs to ADMIN role via `/auth/sessions` 2. Re-authenticate with correct admin credentials 3. If still failing, use Emergency Shutdown Procedure |
| API shutdown returns 404 | `{"detail": "Not Found"}` | 1. Verify endpoint URL: `GET /system/shutdown` not found 2. Check application logs for routing errors 3. Use Emergency Shutdown Procedure |
| Process hangs after SIGTERM | `ps` still shows Uvicorn after 10s | 1. Wait additional 10 seconds 2. Send SIGKILL: `kill -9 <PID>` 3. Verify port release: `lsof -i :8000` |
| Database corruption after crash | `sqlite3` integrity check fails | 1. Stop all processes 2. Restore from backup: `cp data/dats.db.backup dats.db` 3. Run `sqlite3 dats.db "PRAGMA integrity_check;"` 4. Restart and validate |
| Docker container not stopping | `docker stop` hangs | 1. Use `docker stop -t 30 DATS-BETA-CANDIDATE` 2. If still hung: `docker kill DATS-BETA-CANDIDATE` 3. Remove: `docker rm DATS-BETA-CANDIDATE` |
| Session tokens still valid post-restart | Security concern | Expected behavior: sessions are in-memory and reset on restart. If persistent sessions observed, escalate to engineering immediately. |
| Shutdown initiated but trades still active | `GET /orders` shows open positions | 1. Cancel all open orders via API before shutdown 2. If shutdown already initiated, wait for graceful completion 3. Check logs for trade finalization status |

---

## 6. Related Runbooks

- [RB-001: Initial Deployment](RB-001-INITIAL-DEPLOYMENT.md)
- [RB-002: System Startup](RB-002-SYSTEM-STARTUP.md)
- [RB-004: Daily Operator Workflow](RB-004-DAILY-OPERATOR-WORKFLOW.md)
- [RB-009: Upgrade Procedure](RB-009-UPGRADE-PROCEDURE.md)

---

## 7. Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-08 | Initial version |
