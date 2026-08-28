# RB-008: Restore Procedure

**Version:** 1.0
**Date:** 2026-08-08
**Platform:** DATS Beta v1.0
**Audience:** OPERATOR, ADMIN

---

## 1. Purpose

Restore the DATS platform from a verified backup archive to a clean target directory, validate file integrity, run the full test suite, and confirm operational readiness.

## 2. Preconditions

| Item | Requirement | Verification |
|------|-------------|------------|
| Valid Backup Archive | ZIP or tar.gz file exists with matching checksum | `ls /backup/DATS-BETA-CANDIDATE_backup_*.zip` and `.sha256` present |
| Checksum Verified | SHA-256 checksum matches archive | `sha256sum -c *.sha256` returns `OK` |
| Clean Target Directory | `/opt/DATS-BETA-CANDIDATE-restore/` does not exist or is empty | `test ! -d /opt/DATS-BETA-CANDIDATE-restore/` or `ls -A /opt/DATS-BETA-CANDIDATE-restore/` returns empty |
| Python 3.12 Available | `python3.12` executable in `$PATH` | `python3.12 --version` returns `Python 3.12.x` |
| Dependencies Installable | `pip` available and network access for PyPI | `pip --version` succeeds |
| Server Stopped | FastAPI server not running on port 8000 | `lsof -i :8000` returns no output |

## 3. Procedure

### Step 1: Select Backup Archive and Verify Integrity

List available backups and identify the target:

```bash
ls -lt /backup/DATS-BETA-CANDIDATE_backup_*.zip /backup/DATS-BETA-CANDIDATE_backup_*.tar.gz
```

Select the most recent valid backup. Set the archive path:

```bash
export ARCHIVE="/backup/DATS-BETA-CANDIDATE_backup_20260808_093012.zip"
export CHECKSUM="/backup/DATS-BETA-CANDIDATE_backup_20260808_093012.zip.sha256"
```

Verify the checksum:

```bash
cd /backup && sha256sum -c "$CHECKSUM"
```

**Expected outcome:**
```
DATS-BETA-CANDIDATE_backup_20260808_093012.zip: OK
```

If checksum verification fails, **do not proceed**. See Recovery Procedure "Checksum mismatch."

### Step 2: Verify Manifest Exists and Is Valid

```bash
ls /backup/DATS-BETA-CANDIDATE_backup_manifest_20260808_093015.json
python3 -m json.tool /backup/DATS-BETA-CANDIDATE_backup_manifest_20260808_093015.json > /dev/null && echo "Manifest valid"
```

**Expected outcome:**
```
Manifest valid
```

### Step 3: Create Clean Target Directory

```bash
mkdir -p /opt/DATS-BETA-CANDIDATE-restore
cd /opt/DATS-BETA-CANDIDATE-restore
test "$(ls -A .)" && echo "WARNING: Directory not empty" || echo "Directory clean"
```

**Expected outcome:**
```
Directory clean
```

If the directory is not empty, do not proceed. Archive existing contents first:
```bash
tar -czf /backup/pre-restore-snapshot_$(date +%Y%m%d_%H%M%S).tar.gz /opt/DATS-BETA-CANDIDATE-restore/
rm -rf /opt/DATS-BETA-CANDIDATE-restore/*
```

### Step 4: Extract ZIP Archive

```bash
cd /opt/DATS-BETA-CANDIDATE-restore
unzip "$ARCHIVE"
```

**Expected outcome:**
```
Archive:  /backup/DATS-BETA-CANDIDATE_backup_20260808_093012.zip
  inflating: app/main.py
  inflating: app/routers/auth.py
  inflating: config/settings.py
  inflating: data/
  inflating: tests/
  inflating: requirements.txt
  inflating: .env.example
```

If using the tar.gz archive instead:

```bash
cd /opt/DATS-BETA-CANDIDATE-restore
tar -xzf /backup/DATS-BETA-CANDIDATE_backup_20260808_093015.tar.gz
```

**Expected outcome:** Silent extraction with no errors. Verify with `ls`.

### Step 5: Verify Extracted File Structure

```bash
find /opt/DATS-BETA-CANDIDATE-restore -type f | sort
```

**Expected outcome:**
```
/opt/DATS-BETA-CANDIDATE-restore/app/main.py
/opt/DATS-BETA-CANDIDATE-restore/app/routers/auth.py
/opt/DATS-BETA-CANDIDATE-restore/app/routers/decisions.py
/opt/DATS-BETA-CANDIDATE-restore/app/routers/execution.py
/opt/DATS-BETA-CANDIDATE-restore/app/routers/orders.py
/opt/DATS-BETA-CANDIDATE-restore/app/routers/positions.py
/opt/DATS-BETA-CANDIDATE-restore/config/settings.py
/opt/DATS-BETA-CANDIDATE-restore/requirements.txt
/opt/DATS-BETA-CANDIDATE-restore/tests/test_auth.py
/opt/DATS-BETA-CANDIDATE-restore/tests/test_orders.py
/opt/DATS-BETA-CANDIDATE-restore/tests/test_positions.py
/opt/DATS-BETA-CANDIDATE-restore/tests/test_decisions.py
/opt/DATS-BETA-CANDIDATE-restore/tests/test_execution.py
/opt/DATS-BETA-CANDIDATE-restore/tests/test_portfolio.py
```

### Step 6: Verify Critical Files Present

```bash
for f in app/main.py config/settings.py requirements.txt tests/test_auth.py; do
  if [ -f "/opt/DATS-BETA-CANDIDATE-restore/$f" ]; then
    echo "OK: $f"
  else
    echo "MISSING: $f"
  fi
done
```

**Expected outcome:**
```
OK: app/main.py
OK: config/settings.py
OK: requirements.txt
OK: tests/test_auth.py
```

No "MISSING" lines should appear.

### Step 7: Create Python Virtual Environment and Install Dependencies

```bash
cd /opt/DATS-BETA-CANDIDATE-restore
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**Expected outcome:**
```
Successfully installed fastapi uvicorn pydantic pytest httpx ...
```

No `ERROR` lines in pip output.

### Step 8: Configure Environment

```bash
cp /opt/DATS-BETA-CANDIDATE-restore/.env.example /opt/DATS-BETA-CANDIDATE-restore/.env
```

Edit `.env` to set required values:

```bash
cat >> /opt/DATS-BETA-CANDIDATE-restore/.env << 'EOF'
TRADING_PAPER_TRADING=true
DATABASE_URL=sqlite:///./data/dats.db
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
AUDIT_LOG_ENABLED=true
EOF
```

**Expected outcome:** `.env` file created with production-ready settings.

### Step 9: Run Full Test Suite

```bash
cd /opt/DATS-BETA-CANDIDATE-restore
source venv/bin/activate
pytest tests/ -v --tb=short 2>&1 | tee /tmp/restore_test_results.log
```

**Expected outcome:**
```
============================= test session starts ==============================
platform linux -- Python 3.12.x, pytest-8.x.x, pluggy-1.x.x
rootdir: /opt/DATS-BETA-CANDIDATE-restore
collected 183 items

tests/test_auth.py ......................                                [ 12%]
tests/test_orders.py ..........................                        [ 27%]
tests/test_positions.py ........................                         [ 43%]
tests/test_portfolio.py ......................                           [ 57%]
tests/test_decisions.py ............................                     [ 76%]
tests/test_execution.py ............................                     [ 93%]
tests/test_audit.py ...............                                      [100%]

============================== 183 passed in 4.52s ===========================
```

### Step 10: Start the FastAPI Server

```bash
cd /opt/DATS-BETA-CANDIDATE-restore
source venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/dats_restore_server.log 2>&1 &
echo $! > /tmp/dats_restore_server.pid
sleep 3
curl -s http://localhost:8000/health | jq .
```

**Expected outcome:**
```json
{"status": "ok"}
```

### Step 11: Validate Key Endpoints Respond

```bash
curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "operator", "password": "operator_pass"}' | jq '{token_type, role}'
```

**Expected outcome:**
```json
{
  "token_type": "bearer",
  "role": "OPERATOR"
}
```

Test a protected endpoint:

```bash
curl -s -X GET http://localhost:8000/portfolio/summary \
  -H "Authorization: Bearer $(curl -s -X POST http://localhost:8000/auth/login -H 'Content-Type: application/json' -d '{"username":"operator","password":"operator_pass"}' | jq -r '.access_token')" | jq 'keys'
```

**Expected outcome:**
```json
[
  "total_value",
  "cash",
  "positions_value"
]
```

### Step 12: Confirm Operational Readiness

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/docs > /dev/null && echo "OpenAPI docs reachable"
```

**Expected outcome:**
```
{"status": "ok"}
OpenAPI docs reachable
```

## 4. Validation Checks

| # | Check | Expected Result | Method |
|---|-------|-----------------|--------|
| 1 | Checksum verified | `sha256sum -c` returns `OK` | `sha256sum -c *.sha256` |
| 2 | Manifest valid | `python3 -m json.tool` exits 0 | JSON validation on manifest |
| 3 | Target directory clean | No pre-existing files | `test ! "$(ls -A /opt/DATS-BETA-CANDIDATE-restore/)"` |
| 4 | Extraction complete | All key files present | `find` + `ls` listing |
| 5 | Critical files present | `main.py`, `settings.py`, `requirements.txt` exist | File existence check loop |
| 6 | Virtual environment created | `venv/bin/python` exists | `ls venv/bin/python` |
| 7 | Dependencies installed | `pip list` shows `fastapi`, `uvicorn`, `pytest` | `pip list \| grep -E "fastapi\|uvicorn\|pytest"` |
| 8 | All tests pass | `183 passed, 0 failed` | `pytest tests/ -v` |
| 9 | Server starts | `curl /health` returns `{"status": "ok"}` | Health endpoint check |
| 10 | Auth endpoint works | Login returns valid token and role | `POST /auth/login` |
| 11 | Protected endpoints reachable | `GET /portfolio/summary` returns valid JSON | Authenticated API call |
| 12 | OpenAPI docs available | `/docs` returns HTML (HTTP 200) | `curl /docs` |

## 5. Recovery Procedures

| Scenario | Symptom | Recovery Steps |
|----------|---------|----------------|
| Checksum mismatch | Step 1 returns `FAILED` | 1. Verify correct `.sha256` file selected<br>2. Re-download archive from secondary backup location<br>3. If no valid archive, escalate to Admin and check backup media integrity |
| Extraction fails | Step 4 returns `unzip: cannot find` or `tar: Error` | 1. Verify archive path is correct: `ls "$ARCHIVE"`<br>2. Check archive is not truncated: `unzip -t "$ARCHIVE"`<br>3. If corrupted, use alternative archive format (tar.gz if ZIP fails, or vice versa) |
| Missing files after extraction | Step 6 reports `MISSING` files | 1. Check archive contents: `unzip -l "$ARCHIVE" \| grep missing_file`<br>2. If file was excluded during backup, manually copy from source or regenerate<br>3. If critical file missing, use older backup archive |
| pip install fails | Step 7 returns `Could not find a version` | 1. Check Python version: `python3.12 --version`<br>2. Upgrade pip: `pip install --upgrade pip`<br>3. Verify network: `curl https://pypi.org`<br>4. If offline, use pre-downloaded wheels from `/data/wheels/` |
| Tests fail | Step 9 shows `< 183 passed` | 1. Review test output: `cat /tmp/restore_test_results.log`<br>2. Check `.env` configuration: `cat .env`<br>3. Verify database path is writable<br>4. If test failures are in non-critical modules, document and proceed with caution<br>5. If auth or order tests fail, **do not proceed** — fix before production use |
| Server fails to start | Step 10 returns connection refused | 1. Check server logs: `cat /tmp/dats_restore_server.log`<br>2. Verify port 8000 not in use: `lsof -i :8000`<br>3. Check `uvicorn` installed: `which uvicorn`<br>4. Try foreground start: `uvicorn app.main:app --host 0.0.0.0 --port 8000` to see errors<br>5. Fix import errors, then retry |
| Endpoints return 401/403 | Step 11 returns unauthorized | 1. Verify `.env` has correct `JWT_SECRET_KEY`<br>2. Re-authenticate: `POST /auth/login`<br>3. Check token not expired<br>4. Verify RBAC roles loaded: `GET /auth/me` |
| OpenAPI docs unreachable | Step 12 returns 404 | 1. Verify FastAPI app mounted at correct path<br>2. Check `app/main.py` includes `app = FastAPI()` with docs enabled<br>3. Ensure no middleware blocks `/docs` route |

## 6. Related Runbooks

- [RB-005: Paper Trading Session](RB-005-PAPER-TRADING-SESSION.md)
- [RB-006: Decision Review Workflow](RB-006-DECISION-REVIEW-WORKFLOW.md)
- [RB-007: Backup Procedure](RB-007-BACKUP-PROCEDURE.md)

## 7. Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-08 | Initial version |
