# RB-002: System Startup

**Version:** 1.0
**Date:** 2026-08-08
**Platform:** DATS Beta v1.0
**Audience:** Operator / Admin

---

## 1. Purpose

Start the DATS Beta v1.0 trading platform and verify that all core endpoints are responsive and healthy.

---

## 2. Preconditions

| Item | Requirement | Verification |
|------|-------------|------------|
| Deployment | RB-001 (Initial Deployment) completed | Check for `/opt/DATS-BETA-CANDIDATE/src/main.py` |
| Environment | `.env` file present and configured | `ls -la /opt/DATS-BETA-CANDIDATE/.env` |
| Dependencies | Python packages installed (local) OR Docker image built | `pip list \| grep fastapi` OR `docker images \| grep DATS-BETA-CANDIDATE` |
| Port | TCP port 8000 available on target host | `lsof -i :8000` returns empty |
| Database | SQLite database file writable or DATABASE_URL valid | `test -w /opt/DATS-BETA-CANDIDATE/` |
| Network | localhost resolves to 127.0.0.1 | `ping -c 1 localhost` |

---

## 3. Procedure

### Step 1: Navigate to Project Directory

```bash
cd /opt/DATS-BETA-CANDIDATE
```

**Expected outcome:** Current working directory is `/opt/DATS-BETA-CANDIDATE/`.

### Step 2A: Start via Docker

```bash
docker start DATS-BETA-CANDIDATE 2>/dev/null || docker run -d \
  --name DATS-BETA-CANDIDATE \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  DATS-BETA-CANDIDATE:1.0.0-beta
```

**Expected outcome:** Docker container `DATS-BETA-CANDIDATE` starts in detached mode. Output shows a container ID.

### Step 2B: Start via Local Python

```bash
source venv/bin/activate
nohup uvicorn src.main:app --host 0.0.0.0 --port 8000 > dats.log 2>&1 &
echo $! > dats.pid
```

**Expected outcome:** Process starts in background. PID written to `dats.pid`.

### Step 3: Wait for Application Startup

```bash
sleep 5
```

**Expected outcome:** Sufficient time elapsed for FastAPI application initialization.

### Step 4: Verify Process is Running

**Docker:**
```bash
docker ps --filter name=DATS-BETA-CANDIDATE
```

**Expected outcome:** Container shows status `Up` with port mapping `0.0.0.0:8000->8000/tcp`.

**Local:**
```bash
ps aux | grep uvicorn | grep -v grep
```

**Expected outcome:** Uvicorn process visible with `src.main:app` and `--port 8000`.

### Step 5: Check Application Logs

**Docker:**
```bash
docker logs --tail 50 DATS-BETA-CANDIDATE
```

**Local:**
```bash
tail -n 50 dats.log
```

**Expected outcome:** Log contains:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```
No ERROR or CRITICAL level messages.

### Step 6: Verify Health Endpoint

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

### Step 7: Verify Status Endpoint

```bash
curl -s http://localhost:8000/status/ | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "status": "ok"
}
```

### Step 8: Verify System Version

```bash
curl -s http://localhost:8000/system/version | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "version": "1.0.0-beta",
    "release": "Alpha Release Candidate",
    "sprint": "S17+",
    "build_date": "2026-08-08",
    "api_version": "v1"
}
```

### Step 9: Verify System State

```bash
curl -s http://localhost:8000/system/state | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "status": "HEALTHY"
}
```

### Step 10: Verify System Capabilities

```bash
curl -s http://localhost:8000/system/capabilities | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "capabilities_count": 32,
    "readiness_percentage": 100.0,
    "validated": true
}
```

### Step 11: Verify Configuration Validity

```bash
curl -s http://localhost:8000/config/validate | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "valid": true,
    "warnings": [],
    "errors": []
}
```

---

## 4. Validation Checks

| # | Check | Expected Result | Method |
|---|-------|-----------------|--------|
| 1 | Process running | Uvicorn active | `ps aux \| grep uvicorn` (local) OR `docker ps` (Docker) |
| 2 | Port binding | TCP 8000 listening | `ss -tlnp \| grep 8000` |
| 3 | Health endpoint | HTTP 200, `status: "ok"` | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health/` |
| 4 | Status endpoint | HTTP 200, `status: "ok"` | `curl -s http://localhost:8000/status/` |
| 5 | Version endpoint | HTTP 200, `version: "1.0.0-beta"` | `curl -s http://localhost:8000/system/version` |
| 6 | System state | HTTP 200, `status: "HEALTHY"` | `curl -s http://localhost:8000/system/state` |
| 7 | Capabilities | HTTP 200, `readiness_percentage: 100.0` | `curl -s http://localhost:8000/system/cabilities` |
| 8 | Config valid | HTTP 200, `valid: true` | `curl -s http://localhost:8000/config/validate` |
| 9 | Logs clean | No ERROR or CRITICAL entries | `docker logs DATS-BETA-CANDIDATE 2>&1 \| grep -E "ERROR\|CRITICAL"` (should be empty) |

---

## 5. Recovery Procedures

| Scenario | Symptom | Recovery Steps |
|----------|---------|----------------|
| Port conflict | `Address already in use` on startup | 1. Identify blocking process: `lsof -i :8000` 2. Kill process or change port: add `--port 8001` 3. Update firewall/downstream config |
| Import error | `ModuleNotFoundError: No module named 'src'` | 1. Ensure virtual environment activated: `source venv/bin/activate` 2. Verify in project root: `pwd` should show `/opt/DATS-BETA-CANDIDATE` 3. Set PYTHONPATH: `export PYTHONPATH=/opt/DATS-BETA-CANDIDATE` 4. Reinstall: `pip install -r requirements.txt` |
| Database locked | `sqlite3.OperationalError: database is locked` | 1. Check for stale process: `lsof \| grep dats.db` 2. Kill stale process 3. Verify file permissions: `ls -la dats.db` 4. Restart application |
| Docker container exits immediately | `docker ps` shows no container | 1. Check logs: `docker logs DATS-BETA-CANDIDATE` 2. Verify `.env` file syntax (no spaces around `=`) 3. Check volume permissions: `ls -la data/` 4. Start interactively to debug |
| Health endpoint returns 500 | Internal server error | 1. Check logs for full traceback 2. Verify all `.env` required keys present 3. Check disk space: `df -h` 4. Restart application 5. If persistent, escalate to engineering |
| Startup timeout | Application takes >30s to start | 1. Check system resources: `top`, `free -h` 2. Check for network dependency timeouts 3. Verify DNS resolution: `nslookup pypi.org` 4. Restart with `LOG_LEVEL=DEBUG` for detail |
| Dependency version mismatch | `AttributeError` or `ImportError` from package | 1. Check `requirements.txt` versions 2. Clean install: `pip install --force-reinstall -r requirements.txt` 3. Verify Python 3.12.x: `python3 --version` |

---

## 6. Related Runbooks

- [RB-001: Initial Deployment](RB-001-INITIAL-DEPLOYMENT.md)
- [RB-003: System Shutdown](RB-003-SYSTEM-SHUTDOWN.md)
- [RB-004: Daily Operator Workflow](RB-004-DAILY-OPERATOR-WORKFLOW.md)
- [RB-009: Upgrade Procedure](RB-009-UPGRADE-PROCEDURE.md)

---

## 7. Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-08 | Initial version |
