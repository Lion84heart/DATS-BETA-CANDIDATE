# RB-001: Initial Deployment

**Version:** 1.0
**Date:** 2026-08-08
**Platform:** DATS Beta v1.0
**Audience:** Engineering / DevOps

---

## 1. Purpose

Deploy the DATS Beta v1.0 institutional trading platform from source to a target environment for the first time, verifying all dependencies, configuration, and test suite integrity.

---

## 2. Preconditions

| Item | Requirement | Verification |
|------|-------------|------------|
| Hardware | x86_64 CPU, 2+ cores, 4GB+ RAM, 10GB+ free disk | `lscpu && free -h && df -h` |
| Operating System | Ubuntu 22.04 LTS, macOS 14+, or RHEL 9+ | `lsb_release -a` or `sw_vers` |
| Python | Python 3.12.x installed and on PATH | `python3 --version` |
| Docker | Docker Engine 24.0+ (for Docker path) | `docker --version && docker compose version` |
| Git | Git 2.30+ | `git --version` |
| Network | Outbound HTTPS to GitHub and PyPI | `curl -I https://github.com` |
| Shell | Bash or compatible shell | `echo $SHELL` |
| Ports | TCP port 8000 available | `lsof -i :8000 || echo "Port available"` |

---

## 3. Procedure

### Step 1: Clone the Repository

```bash
cd /opt
git clone https://github.com/dats-institutional/DATS-BETA-CANDIDATE.git
cd DATS-BETA-CANDIDATE
```

**Expected outcome:** Repository cloned into `/opt/DATS-BETA-CANDIDATE/` with `src/` and `tests/` directories visible.

### Step 2: Verify Repository Structure

```bash
ls -la
```

**Expected outcome:** Directory listing contains at minimum:
```
src/
tests/
Dockerfile
docker-compose.yml (or will be created)
.env.example
requirements.txt
pyproject.toml (if present)
```

### Step 3: Create Environment Configuration

```bash
cp .env.example .env
```

**Expected outcome:** A new `.env` file is created in the project root.

### Step 4: Edit Environment Configuration

```bash
nano .env
```

Set at minimum the following values:
```
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO
SECRET_KEY=<generate with openssl rand -hex 32>
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<strong-password>
DATABASE_URL=sqlite:///./dats.db
```

**Expected outcome:** `.env` file saved with all required variables defined.

### Step 5A: Deploy via Docker (Recommended)

```bash
docker build -t DATS-BETA-CANDIDATE:1.0.0-beta .
```

**Expected outcome:** Docker image `DATS-BETA-CANDIDATE:1.0.0-beta` built successfully.

### Step 6A: Run Docker Container

```bash
docker run -d \
  --name DATS-BETA-CANDIDATE \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  DATS-BETA-CANDIDATE:1.0.0-beta
```

**Expected outcome:** Container starts and binds to host port 8000.

### Step 5B: Deploy via Local Python

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**Expected outcome:** Virtual environment created and all Python dependencies installed without errors.

### Step 6B: Run Local Instance

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

**Expected outcome:** Uvicorn server starts with output:
```
INFO:     Started server process [N]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### Step 7: Run Test Suite

In a second terminal (or if running in background):

```bash
cd /opt/DATS-BETA-CANDIDATE
source venv/bin/activate
pytest tests/ -v
```

**Expected outcome:** All 183 tests pass with output:
```
==================== 183 passed in X.XXs ====================
```

---

## 4. Validation Checks

| # | Check | Expected Result | Method |
|---|-------|-----------------|--------|
| 1 | Health endpoint | `{"status": "ok", "version": "1.0.0-beta"}` | `curl -s http://localhost:8000/health/ \| python3 -m json.tool` |
| 2 | Status endpoint | `{"status": "ok"}` | `curl -s http://localhost:8000/status/ \| python3 -m json.tool` |
| 3 | System version | `{"version": "1.0.0-beta", "release": "Alpha Release Candidate", "sprint": "S17+", "build_date": "2026-08-08", "api_version": "v1"}` | `curl -s http://localhost:8000/system/version \| python3 -m json.tool` |
| 4 | System state | `{"status": "HEALTHY"}` | `curl -s http://localhost:8000/system/state \| python3 -m json.tool` |
| 5 | Test suite | 183/183 passed | `pytest tests/ -v --tb=short` |
| 6 | Config validation | `{"valid": true, "warnings": [], "errors": []}` | `curl -s http://localhost:8000/config/validate \| python3 -m json.tool` |
| 7 | Process listening | Uvicorn on TCP 8000 | `lsof -i :8000` or `ss -tlnp \| grep 8000` |

---

## 5. Recovery Procedures

| Scenario | Symptom | Recovery Steps |
|----------|---------|----------------|
| Health check fails (connection refused) | `curl: (7) Failed to connect` | 1. Check process: `ps aux \| grep uvicorn` 2. Check logs: `docker logs DATS-BETA-CANDIDATE` 3. Verify port: `lsof -i :8000` 4. Restart service |
| Health check returns 500 | Internal server error in JSON | 1. Check application logs for traceback 2. Verify `.env` file has all required keys 3. Check database connectivity 4. Restart and retry |
| Import error on startup | `ModuleNotFoundError` in logs | 1. Ensure virtual environment is activated: `source venv/bin/activate` 2. Reinstall dependencies: `pip install -r requirements.txt` 3. Verify Python version: `python3 --version` (must be 3.12.x) |
| Docker build fails | Error during `docker build` | 1. Check Dockerfile syntax 2. Verify Docker daemon: `docker info` 3. Check network to Docker Hub/PyPI 4. Retry with `--no-cache` flag |
| Port 8000 already in use | `Address already in use` | 1. Identify process: `lsof -i :8000` 2. Stop conflicting process or change port: `uvicorn src.main:app --port 8001` 3. Update any downstream config to match new port |
| Test failures | `pytest` reports < 183 passed | 1. Check Python version is exactly 3.12.x 2. Verify all dependencies installed: `pip list` 3. Run specific failing test with: `pytest tests/<path> -v -s` 4. Check `.env` has all required variables |
| Container exits immediately | `docker ps` shows no running container | 1. Inspect logs: `docker logs DATS-BETA-CANDIDATE` 2. Verify `.env` file is mounted correctly 3. Check `APP_PORT` matches exposed port 4. Run interactively to debug: `docker run --rm -it --env-file .env DATS-BETA-CANDIDATE:1.0.0-beta` |

---

## 6. Related Runbooks

- [RB-002: System Startup](RB-002-SYSTEM-STARTUP.md)
- [RB-003: System Shutdown](RB-003-SYSTEM-SHUTDOWN.md)
- [RB-004: Daily Operator Workflow](RB-004-DAILY-OPERATOR-WORKFLOW.md)
- [RB-009: Upgrade Procedure](RB-009-UPGRADE-PROCEDURE.md)

---

## 7. Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-08 | Initial version |
