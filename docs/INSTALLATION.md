# DATS Installation Guide

**Version:** 1.0.0-beta  
**Last Updated:** 2026-08-08  
**Audience:** Platform Engineers, DevOps

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Install](#quick-install)
3. [Manual Installation](#manual-installation)
4. [Docker Installation](#docker-installation)
5. [Verification](#verification)
6. [Uninstall](#uninstall)

---

## Prerequisites

### Required

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.12+ | Runtime and dependency management |
| pip | 24.0+ | Python package installer |
| Git | 2.40+ | Source control |

### Optional (Recommended)

| Component | Version | Purpose |
|-----------|---------|---------|
| Docker | 25.0+ | Containerized deployment |
| Docker Compose | 2.24+ | Multi-service orchestration |
| PostgreSQL | 16+ | Production database |
| Redis | 7+ | Caching and session store |

### System Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 2 GB | 4 GB |
| CPU | 1 core | 2 cores |
| Disk | 2 GB free | 10 GB free |
| Network | Outbound HTTP/HTTPS | Low-latency to exchange APIs |

---

## Quick Install

The project includes an automated setup script that handles environment creation, dependency installation, and initial verification.

```bash
# Clone the repository
git clone <repository-url> DATS-BETA-CANDIDATE
cd DATS-BETA-CANDIDATE

# Run automated setup
./scripts/setup.sh
```

The setup script performs the following:
1. Validates Python 3.12+ is available
2. Creates a virtual environment (`.venv`)
3. Installs all dependencies from `pyproject.toml`
4. Copies `.env.example` to `.env` if not present
5. Creates required data directories (`data/exports`, `data/logs`, `data/backups`)
6. Runs a subset of tests to verify the installation

---

## Manual Installation

Use manual installation when you need fine-grained control over the environment or the automated script fails.

### Step 1: Clone Repository

```bash
git clone <repository-url> DATS-BETA-CANDIDATE
cd DATS-BETA-CANDIDATE
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv .venv

# Activate
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate            # Windows
```

### Step 3: Install Dependencies

```bash
# Upgrade build tools
pip install --upgrade pip setuptools wheel

# Install project in editable mode with all dependencies
pip install -e "."

# Install development dependencies (optional)
pip install -e ".[dev]"
```

### Step 4: Environment Configuration

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your settings
# Minimum required changes for local development:
#   - SECURITY_JWT_SECRET (generate a strong secret)
#   - DB_PASSWORD (if using external PostgreSQL)
```

### Step 5: Create Data Directories

```bash
mkdir -p data/exports data/logs data/backups
```

### Step 6: Verify Installation

```bash
# Set PYTHONPATH
export PYTHONPATH="src:$PYTHONPATH"

# Run tests
python3 -m pytest tests/ -q --tb=short

# Or run the health check script
./scripts/health_check.sh
```

---

## Docker Installation

Docker provides the simplest path to a fully functional environment with all services (app, PostgreSQL, Redis) pre-configured.

### Step 1: Clone Repository

```bash
git clone <repository-url> DATS-BETA-CANDIDATE
cd DATS-BETA-CANDIDATE
```

### Step 2: Configure Environment

```bash
# Review docker-compose.yml environment variables
# Override via .env or docker-compose.override.yml if needed
```

The included `docker-compose.yml` provides sensible defaults:

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| dats | Build from Dockerfile | 8000 | FastAPI application |
| db | postgres:16-alpine | 5432 | PostgreSQL database |
| redis | redis:7-alpine | 6379 | Cache and sessions |

### Step 3: Build and Start

```bash
# Using the start script (recommended)
./scripts/start.sh docker

# Or manually
docker-compose up -d --build
```

### Step 4: Verify

```bash
# Check container status
docker-compose ps

# View logs
docker-compose logs -f dats

# Health check
curl http://localhost:8000/health/
```

### Step 5: Stop Services

```bash
# Using the stop script
./scripts/stop.sh docker

# Or manually
docker-compose down

# To remove volumes (WARNING: deletes data)
docker-compose down -v
```

---

## Verification

After installation, verify the platform is operational:

### 1. Health Endpoint

```bash
curl http://localhost:8000/health/
```

Expected response:
```json
{
  "status": 3,
  "checks": {
    "database": {"healthy": true, "message": "connected"},
    "redis": {"healthy": true, "message": "connected"}
  },
  "timestamp": "2026-08-08T12:00:00Z"
}
```

### 2. System Status

```bash
curl http://localhost:8000/status/
```

### 3. Version Check

```bash
curl http://localhost:8000/system/version
```

Expected:
```json
{"version": "1.0.0-beta", "name": "DATS"}
```

### 4. Automated Health Script

```bash
./scripts/health_check.sh
```

Expected output:
```
=== DATS Health Check ===
Timestamp: 2026-08-08T12:00:00+00:00

[PASS] /health/ => "status": 3
[PASS] /status/ => "state"
[PASS] /system/version => "version": "1.0.0-beta"
[PASS] /diagnostics/runtime => "python_version"
[PASS] /diagnostics/performance => "timestamp"
[PASS] /config/validate => "valid": true

=== ALL CHECKS PASSED ===
```

### 5. Dashboard Access

| URL | Description |
|-----|-------------|
| `http://localhost:8000/` | Main SPA login |
| `http://localhost:8000/operator` | Operator console |
| `http://localhost:8000/dashboard` | Decision review dashboard |
| `http://localhost:8000/docs` | Auto-generated OpenAPI docs |

---

## Uninstall

### Local Installation

```bash
# Deactivate virtual environment
deactivate

# Remove virtual environment and data
rm -rf .venv
rm -rf data/
rm -f .env .dats.pid

# Remove __pycache__ files
find . -type d -name __pycache__ -exec rm -rf {} +
```

### Docker Installation

```bash
# Stop and remove containers, networks, volumes
docker-compose down -v

# Remove built image
docker rmi dats-beta-candidate:1.0.0-beta
```

---

## Troubleshooting Installation

| Symptom | Cause | Resolution |
|---------|-------|------------|
| `python3: command not found` | Python not installed or not in PATH | Install Python 3.12+ and ensure it's in PATH |
| `pip install` fails with compilation errors | Missing build dependencies | Install `gcc`, `g++`, `libpq-dev` (see Dockerfile builder stage) |
| `ModuleNotFoundError: api` | PYTHONPATH not set | Run `export PYTHONPATH="src:$PYTHONPATH"` |
| `connection refused` on port 8000 | Service not started or port conflict | Check if another service uses port 8000; verify startup logs |
| Database connection errors | PostgreSQL not running or wrong credentials | Verify `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` in `.env` |
| Health check returns `"status": "UNKNOWN"` | Bootstrap failure | Check application logs for bootstrap errors |

---

*DATS Beta v1.0 — Engineering Documentation*
