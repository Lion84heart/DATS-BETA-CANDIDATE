# RB-009: Upgrade Procedure

**Version:** 1.0
**Date:** 2026-08-08
**Platform:** DATS Beta v1.0
**Audience:** Engineering / Admin

---

## 1. Purpose

Upgrade the DATS Beta v1.0 trading platform from the current version to a newer release, with full backup, test validation, and rollback capability.

---

## 2. Preconditions

| Item | Requirement | Verification |
|------|-------------|------------|
| Current version | Existing deployment running | `curl -s http://localhost:8000/system/version` |
| Backup | Complete backup of current deployment | `ls -la /opt/backups/DATS-BETA-CANDIDATE/` |
| New version | Target version identified (tag, branch, or commit) | `git ls-remote origin <tag>` |
| Permissions | Admin role or shell access to deployment host | `whoami && groups` |
| Downtime window | Scheduled maintenance window agreed | Check change management ticket |
| Test readiness | New version has passing test suite | CI/CD pipeline green for target commit |
| Disk space | Minimum 2GB free for upgrade artifacts | `df -h /opt` |

---

## 3. Procedure

### Step 1: Capture Current Version

```bash
CURRENT_VERSION=$(curl -s http://localhost:8000/system/version | python3 -c "import sys, json; print(json.load(sys.stdin)['version'])")
echo "Current version: $CURRENT_VERSION"
```

**Expected outcome:** Version string printed, e.g., `1.0.0-beta`.

### Step 2: Create Pre-Upgrade Backup

```bash
BACKUP_DIR="/opt/backups/DATS-BETA-CANDIDATE/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -r /opt/DATS-BETA-CANDIDATE/src "$BACKUP_DIR/"
cp /opt/DATS-BETA-CANDIDATE/.env "$BACKUP_DIR/"
cp /opt/DATS-BETA-CANDIDATE/requirements.txt "$BACKUP_DIR/"
cp -r /opt/DATS-BETA-CANDIDATE/tests "$BACKUP_DIR/"
cp /opt/DATS-BETA-CANDIDATE/dats.db "$BACKUP_DIR/" 2>/dev/null
cp /opt/DATS-BETA-CANDIDATE/dats.log "$BACKUP_DIR/" 2>/dev/null
echo "Backup created at: $BACKUP_DIR"
ls -la "$BACKUP_DIR"
```

**Expected outcome:** Backup directory populated with source code, config, tests, and database.

### Step 3: Verify Pre-Upgrade Health

```bash
curl -s http://localhost:8000/health/ | python3 -m json.tool
curl -s http://localhost:8000/config/validate | python3 -m json.tool
curl -s http://localhost:8000/system/state | python3 -m json.tool
```

**Expected outcome:**
- `/health/`: `{"status": "ok", "version": "$CURRENT_VERSION"}`
- `/config/validate`: `{"valid": true, "warnings": [], "errors": []}`
- `/system/state`: `{"status": "HEALTHY"}`

### Step 4: Graceful Shutdown

Follow [RB-003: System Shutdown](RB-003-SYSTEM-SHUTDOWN.md) to gracefully stop the platform.

**Expected outcome:** Process terminated, port 8000 released.

### Step 5: Stash or Tag Current State

```bash
cd /opt/DATS-BETA-CANDIDATE
git tag "pre-upgrade-$(date +%Y%m%d-%H%M%S)"
git stash push -m "pre-upgrade-stash-$(date +%Y%m%d-%H%M%S)"
```

**Expected outcome:** Git tag created. Any local uncommitted changes stashed.

### Step 6: Pull New Code

```bash
git fetch origin
git checkout <TARGET_VERSION_TAG_OR_BRANCH>
```

**Expected outcome:** Repository checked out to target version. `git log --oneline -1` shows target commit.

### Step 7: Review Changelog and Breaking Changes

```bash
cat CHANGELOG.md | head -100
```

**Expected outcome:** Changelog reviewed for breaking changes, new environment variables, or migration requirements.

### Step 8: Update Environment Configuration

```bash
diff .env .env.example
```

**Expected outcome:** Differences between current `.env` and new `.env.example` identified. Add any new required variables to `.env`.

```bash
# Example: if new variables were added
# echo "NEW_FEATURE_ENABLED=true" >> .env
```

### Step 9: Update Python Dependencies

```bash
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**Expected outcome:** All packages installed without errors.

### Step 10: Run Full Test Suite

```bash
pytest tests/ -v --tb=short
```

**Expected outcome:** All 183 tests pass (or target test count for new version).

### Step 11: Run Database Migration (if applicable)

```bash
# If migrations directory exists
python3 -m alembic upgrade head 2>/dev/null || echo "No migrations required"
```

**Expected outcome:** Migrations applied successfully or no migrations needed.

### Step 12: Build New Docker Image (if using Docker)

```bash
docker build -t DATS-BETA-CANDIDATE:<TARGET_VERSION> .
```

**Expected outcome:** Docker image built successfully with target version tag.

### Step 13: Start New Version

**Docker:**
```bash
docker run -d \
  --name DATS-BETA-CANDIDATE-new \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  DATS-BETA-CANDIDATE:<TARGET_VERSION>
```

**Local:**
```bash
source venv/bin/activate
nohup uvicorn src.main:app --host 0.0.0.0 --port 8000 > dats.log 2>&1 &
echo $! > dats.pid
```

**Expected outcome:** Application starts and binds to port 8000.

### Step 14: Wait for Startup and Verify Health

```bash
sleep 10
curl -s http://localhost:8000/health/ | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "status": "ok",
    "version": "<TARGET_VERSION>"
}
```

### Step 15: Verify New Version

```bash
curl -s http://localhost:8000/system/version | python3 -m json.tool
```

**Expected outcome:**
```json
{
    "version": "<TARGET_VERSION>",
    "release": "...",
    "build_date": "...",
    "api_version": "v1"
}
```
Version string differs from pre-upgrade `$CURRENT_VERSION`.

### Step 16: Verify System State

```bash
curl -s http://localhost:8000/system/state | python3 -m json.tool
curl -s http://localhost:8000/system/capabilities | python3 -m json.tool
```

**Expected outcome:**
- `/system/state`: `{"status": "HEALTHY"}`
- `/system/capabilities`: `{"capabilities_count": <N>, "readiness_percentage": 100.0, "validated": true}`

### Step 17: Validate Configuration

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

### Step 18: Smoke Test Core Endpoints

```bash
# Authenticate
SMOKE_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "<ADMIN_PASSWORD>"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# Test protected endpoint
curl -s http://localhost:8000/auth/sessions \
  -H "Authorization: Bearer $SMOKE_TOKEN" \
  | python3 -m json.tool

# Logout
curl -s -X POST http://localhost:8000/auth/logout \
  -H "Authorization: Bearer $SMOKE_TOKEN"
```

**Expected outcome:** Authentication succeeds, sessions list returned, logout succeeds.

### Step 19: Clean Up Old Docker Container (Docker only)

```bash
docker stop DATS-BETA-CANDIDATE 2>/dev/null
docker rm DATS-BETA-CANDIDATE 2>/dev/null
docker rename DATS-BETA-CANDIDATE-new DATS-BETA-CANDIDATE
```

**Expected outcome:** Old container removed. New container renamed to standard name.

### Step 20: Document Upgrade Completion

```bash
echo "$(date -Iseconds) - Upgraded from $CURRENT_VERSION to <TARGET_VERSION>" >> /opt/DATS-BETA-CANDIDATE/upgrade.log
```

**Expected outcome:** Entry appended to upgrade log file.

---

## 4. Validation Checks

| # | Check | Expected Result | Method |
|---|-------|-----------------|--------|
| 1 | Version changed | `version` != pre-upgrade `$CURRENT_VERSION` | `GET /system/version` |
| 2 | Health OK | `status: "ok"` | `GET /health/` |
| 3 | System HEALTHY | `status: "HEALTHY"` | `GET /system/state` |
| 4 | Capabilities ready | `readiness_percentage: 100.0` | `GET /system/capabilities` |
| 5 | Config valid | `valid: true, errors: []` | `GET /config/validate` |
| 6 | Tests pass | 183/183 passed (or target count) | `pytest tests/ -v` |
| 7 | Auth functional | Login returns token and role | `POST /auth/login` |
| 8 | Database intact | `PRAGMA integrity_check` returns `ok` | `sqlite3 dats.db "PRAGMA integrity_check;"` |
| 9 | Port binding | TCP 8000 listening | `ss -tlnp \| grep 8000` |
| 10 | Logs clean | No ERROR during startup | `grep -i error dats.log \| grep -v "INFO.*error"` returns empty |

---

## 5. Recovery Procedures

| Scenario | Symptom | Recovery Steps |
|----------|---------|----------------|
| Upgrade fails (tests fail) | `pytest` reports failures | 1. Note failing tests 2. Do NOT proceed to startup 3. Check out previous version: `git checkout <CURRENT_VERSION>` 4. Re-install previous deps: `pip install -r requirements.txt` 5. Proceed to Rollback Procedure |
| Health check fails after upgrade | `curl` returns 500 or connection refused | 1. Check application logs for error traceback 2. Verify `.env` has all new required variables 3. If unresolvable within 5 minutes, execute Rollback Procedure |
| Database migration fails | `alembic upgrade` errors | 1. Do NOT restart application 2. Restore database from backup: `cp $BACKUP_DIR/dats.db .` 3. Verify integrity: `sqlite3 dats.db "PRAGMA integrity_check;"` 4. Execute Rollback Procedure |
| Version unchanged after pull | `/system/version` still shows old version | 1. Verify correct branch/tag checked out: `git log --oneline -1` 2. Check for cached bytecode: `find . -name "*.pyc" -delete` 3. Restart Python/Uvicorn process 4. If still old version, execute Rollback Procedure |
| Docker image build fails | Error during `docker build` | 1. Check Dockerfile for syntax changes 2. Verify base image availability: `docker pull python:3.12-slim` 3. Check network to registries 4. Build with `--no-cache` if cache corruption suspected 5. If unresolvable, execute Rollback Procedure |
| Missing new environment variables | `KeyError` in logs | 1. Compare `.env` and `.env.example`: `diff .env .env.example` 2. Add missing variables to `.env` 3. Restart application 4. Re-validate |
| Rollback needed | Any critical failure during upgrade | Follow the Rollback Procedure below |

### Rollback Procedure

Execute immediately if any validation check fails and cannot be resolved within 5 minutes.

**Step R1: Stop the new version**
```bash
# Docker
docker stop DATS-BETA-CANDIDATE-new 2>/dev/null
docker rm DATS-BETA-CANDIDATE-new 2>/dev/null

# Local
if [ -f dats.pid ]; then kill $(cat dats.pid) 2>/dev/null; rm -f dats.pid; fi
```

**Step R2: Restore from backup**
```bash
BACKUP_DIR="<path-recorded-in-step-2>"
cp -r "$BACKUP_DIR/src" /opt/DATS-BETA-CANDIDATE/
cp "$BACKUP_DIR/.env" /opt/DATS-BETA-CANDIDATE/
cp "$BACKUP_DIR/requirements.txt" /opt/DATS-BETA-CANDIDATE/
cp "$BACKUP_DIR/dats.db" /opt/DATS-BETA-CANDIDATE/ 2>/dev/null
```

**Step R3: Checkout previous git state**
```bash
git checkout "$CURRENT_VERSION"
```

**Step R4: Restore previous dependencies**
```bash
source venv/bin/activate
pip install -r requirements.txt --force-reinstall
```

**Step R5: Restart previous version**
```bash
# Docker
docker run -d --name DATS-BETA-CANDIDATE -p 8000:8000 --env-file .env DATS-BETA-CANDIDATE:$CURRENT_VERSION

# Local
nohup uvicorn src.main:app --host 0.0.0.0 --port 8000 > dats.log 2>&1 &
echo $! > dats.pid
```

**Step R6: Validate rollback**
```bash
sleep 5
curl -s http://localhost:8000/health/ | python3 -m json.tool
curl -s http://localhost:8000/system/version | python3 -m json.tool
```
Expected: Health OK, version matches `$CURRENT_VERSION`.

**Step R7: Document rollback**
```bash
echo "$(date -Iseconds) - Rollback executed from <TARGET_VERSION> to $CURRENT_VERSION" >> /opt/DATS-BETA-CANDIDATE/upgrade.log
```

---

## 6. Related Runbooks

- [RB-001: Initial Deployment](RB-001-INITIAL-DEPLOYMENT.md)
- [RB-002: System Startup](RB-002-SYSTEM-STARTUP.md)
- [RB-003: System Shutdown](RB-003-SYSTEM-SHUTDOWN.md)
- [RB-004: Daily Operator Workflow](RB-004-DAILY-OPERATOR-WORKFLOW.md)

---

## 7. Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-08 | Initial version |
