# RB-010: Failure Recovery

**Version:** 1.0  
**Date:** 2026-08-08  
**Platform:** DATS Beta v1.0  
**Audience:** Operator, Admin, Engineering

---

## 1. Purpose

Restore platform availability by diagnosing the root cause of a system failure and applying the appropriate recovery steps.

## 2. Preconditions

| Item | Requirement | Verification |
|------|-------------|------------|
| Access to server | SSH or console access to the host running DATS | `ssh <user>@<host>` succeeds |
| Platform directory | Know the DATS installation path | Verify `/opt/DATS-BETA-CANDIDATE/` exists |
| Python 3.12 | Python 3.12 runtime installed | `python3.12 --version` returns `Python 3.12.x` |
| Log access | Read access to application logs | `ls -la /opt/DATS-BETA-CANDIDATE/logs/` succeeds |
| Backup available | Latest configuration backup accessible | `ls -la /opt/DATS-BETA-CANDIDATE/backups/` |
| Service identity | Process owner known (default: `dats`) | `id dats` returns valid user |

## 3. Procedure

### Step 1: Confirm Failure
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health/
```
**Expected outcome:** Returns `000` (connection refused) or `5xx` if service is down.

If the service responds with `200`, the failure may be partial; proceed to [RB-012: Health Verification](RB-012-HEALTH-VERIFICATION.md).

### Step 2: Identify Current Process State
```bash
ps aux | grep -E "(uvicorn|fastapi|dats)" | grep -v grep
netstat -tlnp 2>/dev/null || ss -tlnp | grep 8000
cat /opt/DATS-BETA-CANDIDATE/logs/dats.log | tail -n 50
```
**Expected outcome:** Shows whether a process is bound to port 8000 and reveals the last logged error.

### Step 3: Scenario — Service Won't Start

**Symptom:** `curl http://localhost:8000/health/` returns `000`; process is not running.

```bash
# Check systemd service status
sudo systemctl status DATS-BETA-CANDIDATE

# Attempt manual start and capture full output
cd /opt/DATS-BETA-CANDIDATE
source .venv/bin/activate
uvicorn dats.main:app --host 0.0.0.0 --port 8000 --log-level debug 2>&1 | tee /tmp/dats_startup.log
```

**Expected outcome:** Terminal shows startup logs. If it exits immediately, note the final exception.

**Recovery:**
- If `ModuleNotFoundError`: proceed to Step 5 (Dependency Import Error).
- If `Permission denied`: run `sudo chown -R dats:dats /opt/DATS-BETA-CANDIDATE/` and retry.
- If no error but exits silently: check disk space (Step 8) and memory (Step 7).

### Step 4: Scenario — Port Conflict

**Symptom:** Startup logs contain `Address already in use` for port 8000.

```bash
# Identify the process using port 8000
sudo ss -tlnp | grep 8000
sudo lsof -i :8000

# Kill the conflicting process (only if confirmed non-DATS)
sudo kill -15 <PID>
# Wait 5 seconds, then force-kill if still present
sleep 5
sudo kill -9 <PID> 2>/dev/null || true

# Restart DATS
sudo systemctl restart DATS-BETA-CANDIDATE
```

**Expected outcome:** Port 8000 is free. DATS binds successfully.

### Step 5: Scenario — Dependency Import Error

**Symptom:** Startup fails with `ModuleNotFoundError`, `ImportError`, or `DLL load failed`.

```bash
cd /opt/DATS-BETA-CANDIDATE
source .venv/bin/activate

# Verify virtual environment integrity
pip check

# Re-install dependencies from lock file
pip install -r requirements.lock --force-reinstall --no-deps 2>&1 | tee /tmp/pip_reinstall.log

# Verify critical imports
python -c "import fastapi, uvicorn, pydantic, httpx; print('OK')"
```

**Expected outcome:** `pip check` reports `No broken requirements`. Critical imports succeed.

**Recovery:**
- If `pip check` reports broken requirements: fix the lock file and re-install.
- If import still fails: remove and recreate the virtual environment:
  ```bash
  rm -rf .venv
  python3.12 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.lock
  ```

### Step 6: Scenario — Database Connection Failure

**Symptom:** Startup logs contain `OperationalError`, `Connection refused`, or `database is locked`.

```bash
# Verify database file exists and is writable (SQLite default)
ls -la /opt/DATS-BETA-CANDIDATE/data/dats.db

# Check file permissions
stat /opt/DATS-BETA-CANDIDATE/data/dats.db

# Verify database integrity
sqlite3 /opt/DATS-BETA-CANDIDATE/data/dats.db "PRAGMA integrity_check;"
```

**Expected outcome:** `integrity_check` returns `ok`. File is owned by `dats:dats`.

**Recovery:**
- If file is missing: restore from the latest backup:
  ```bash
  cp /opt/DATS-BETA-CANDIDATE/backups/dats.db.$(date +%Y%m%d) /opt/DATS-BETA-CANDIDATE/data/dats.db
  chown dats:dats /opt/DATS-BETA-CANDIDATE/data/dats.db
  chmod 644 /opt/DATS-BETA-CANDIDATE/data/dats.db
  ```
- If `integrity_check` fails: export data, rebuild, and re-import:
  ```bash
  sqlite3 /opt/DATS-BETA-CANDIDATE/data/dats.db ".dump" > /tmp/dats_dump.sql
  mv /opt/DATS-BETA-CANDIDATE/data/dats.db /opt/DATS-BETA-CANDIDATE/data/dats.db.corrupt
  sqlite3 /opt/DATS-BETA-CANDIDATE/data/dats.db < /tmp/dats_dump.sql
  ```
- If permissions are wrong:
  ```bash
  sudo chown -R dats:dats /opt/DATS-BETA-CANDIDATE/data/
  sudo chmod 644 /opt/DATS-BETA-CANDIDATE/data/dats.db
  ```

### Step 7: Scenario — Memory Exhaustion

**Symptom:** OOM killer messages in `dmesg`; process exits with `Killed`; `MemoryError` in logs.

```bash
# Check current memory state
free -h

# Check OOM killer log
sudo dmesg | grep -i "out of memory\|killed process" | tail -n 10

# Check if swap is available and active
swapon --show

# Check DATS memory baseline
curl -s http://localhost:8000/diagnostics/performance | python -m json.tool
```

**Expected outcome:** Memory usage is below 256MB baseline. Swap is active if configured.

**Recovery:**
- If OOM killed: restart the service and monitor:
  ```bash
  sudo systemctl restart DATS-BETA-CANDIDATE
  sleep 10
  ps aux | grep uvicorn | grep -v grep
  ```
- If memory climbs above 256MB: capture a diagnostic snapshot and restart:
  ```bash
  curl -s http://localhost:8000/diagnostics/performance > /tmp/dats_perf_$(date +%Y%m%d_%H%M%S).json
  sudo systemctl restart DATS-BETA-CANDIDATE
  ```
- If swap is off and memory is low, enable swap (temporary relief):
  ```bash
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  ```

### Step 8: Scenario — Disk Full

**Symptom:** Write errors in logs (`No space left on device`); service fails to start or log.

```bash
# Check disk usage
df -h

# Identify large files in DATS directories
du -sh /opt/DATS-BETA-CANDIDATE/logs/* | sort -rh | head -n 10
du -sh /opt/DATS-BETA-CANDIDATE/data/* | sort -rh | head -n 10

# Check for core dumps
find /opt/DATS-BETA-CANDIDATE -name "core.*" -type f -size +10M
```

**Expected outcome:** Root partition has at least 1GB free. Log files are under 100MB each.

**Recovery:**
- Rotate and compress logs:
  ```bash
  cd /opt/DATS-BETA-CANDIDATE/logs
  mv dats.log dats.log.$(date +%Y%m%d_%H%M%S)
  gzip dats.log.*
  sudo systemctl restart DATS-BETA-CANDIDATE
  ```
- Remove old backups (keep last 7 days):
  ```bash
  cd /opt/DATS-BETA-CANDIDATE/backups
  ls -t dats.db.* | tail -n +8 | xargs -r rm -f
  ```
- Remove core dumps:
  ```bash
  find /opt/DATS-BETA-CANDIDATE -name "core.*" -type f -delete
  ```

### Step 9: Clear Caches and Restart
```bash
# Clear Python bytecode caches
find /opt/DATS-BETA-CANDIDATE -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find /opt/DATS-BETA-CANDIDATE -name "*.pyc" -delete 2>/dev/null || true

# Restart the service
sudo systemctl restart DATS-BETA-CANDIDATE
sleep 5
```
**Expected outcome:** Service restarts without errors.

### Step 10: Verify Recovery
```bash
curl -s http://localhost:8000/health/ | python -m json.tool
curl -s http://localhost:8000/status/ | python -m json.tool
curl -s http://localhost:8000/system/state | python -m json.tool
```
**Expected outcome:** All three endpoints return HTTP 200 with `{"status": "ok"}` or `{"status": "HEALTHY"}`.

### Step 11: Run Test Suite
```bash
cd /opt/DATS-BETA-CANDIDATE
source .venv/bin/activate
pytest tests/ -q --tb=short
```
**Expected outcome:** `183 passed` with `0 failed`.

## 4. Validation Checks

| # | Check | Expected Result | Method |
|---|-------|-----------------|--------|
| 1 | Health endpoint | `{"status": "ok"}` | `curl -s http://localhost:8000/health/` |
| 2 | Status endpoint | `{"status": "ok"}` | `curl -s http://localhost:8000/status/` |
| 3 | System state | `{"status": "HEALTHY"}` | `curl -s http://localhost:8000/system/state` |
| 4 | Diagnostics runtime | JSON with `platform`, `python_version`, `timestamp` | `curl -s http://localhost:8000/diagnostics/runtime` |
| 5 | Config validation | `{"valid": true}` | `curl -s http://localhost:8000/config/validate` |
| 6 | Port binding | Port 8000 in LISTEN state | `ss -tlnp | grep 8000` |
| 7 | Test suite | `183 passed` | `pytest tests/ -q` |
| 8 | Log errors | No ERROR or CRITICAL in last 50 lines | `grep -iE "error|critical" /opt/DATS-BETA-CANDIDATE/logs/dats.log | tail -n 5` returns empty |
| 9 | Memory usage | `< 256 MB` | `curl -s http://localhost:8000/diagnostics/performance | jq '.memory_mb'` |

## 5. Recovery Procedures

| Scenario | Symptom | Recovery Steps |
|----------|---------|----------------|
| Service won't start | Port 8000 not bound; no uvicorn process | Check logs for exception; fix dependency/database/disk issue; `sudo systemctl restart DATS-BETA-CANDIDATE` |
| Port conflict | `Address already in use` on startup | Identify conflicting PID with `lsof -i :8000`; `sudo kill -15 <PID>`; restart DATS |
| Database connection failure | `OperationalError` in logs; `integrity_check` fails | Restore from `/opt/DATS-BETA-CANDIDATE/backups/` or rebuild from `.dump`; fix permissions |
| Dependency import error | `ModuleNotFoundError` on startup | `pip check`; `pip install -r requirements.lock`; recreate `.venv` if persistent |
| Memory exhaustion | OOM killer; `MemoryError`; memory > 256MB | Restart service; clear caches; enable swap; escalate if leak persists |
| Disk full | `No space left on device`; write failures | Rotate logs; remove old backups; delete core dumps; `df -h` confirms > 1GB free |
| All recovery steps exhausted | System still failing after steps 1-11 | Engage engineering with `/tmp/dats_startup.log`, `dmesg`, and full `dats.log` attached |

## 6. Related Runbooks

- [RB-012: Health Verification](RB-012-HEALTH-VERIFICATION.md) — Post-recovery health checks
- [RB-011: Incident Response](RB-011-INCIDENT-RESPONSE.md) — When failure is part of a broader incident
- [RB-013: Performance Verification](RB-013-PERFORMANCE-VERIFICATION.md) — Validate performance after recovery

## 7. Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-08 | Initial version |
