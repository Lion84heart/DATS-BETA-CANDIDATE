# DATS — Institutional AI Trading Platform

**Version:** 1.0.0-beta  
**Release:** Beta Release Candidate  
**Date:** 2026-08-26  
**Status:** Engineering Certified — Release Candidate Accepted

---

## Overview

DATS is an institutional-grade algorithmic trading platform built with Python 3.12 and FastAPI. It provides a complete paper trading environment with real-time decision intelligence, operator dashboards, WebSocket feeds, and comprehensive observability.

### Key Statistics

| Metric | Value |
|--------|-------|
| Capabilities Validated | 32/32 (100%) |
| Test Coverage | 183/183 passing |
| Alpha Release Gates | 7/7 CLOSED |
| API Endpoints | 64 unique routes |
| API Latency (p95) | 7.97ms |
| Throughput | 621 req/sec |
| Memory Footprint | 163.6MB |

---

## Quick Start

### Prerequisites

- Python 3.12+
- Docker and Docker Compose (optional)
- 2GB RAM minimum
- 1 CPU core minimum

### Option 1: Local Setup

```bash
# Clone and enter repository
cd DATS-BETA-CANDIDATE

# Run setup (creates venv, installs deps, runs tests)
./scripts/setup.sh

# Start the platform
./scripts/start.sh local

# Verify health
curl http://localhost:8000/health/

# Access dashboard
open http://localhost:8000/operator
```

### Option 2: Docker Compose

```bash
# Start all services (app, PostgreSQL, Redis)
./scripts/start.sh docker

# Or manually:
docker-compose up -d

# Verify health
curl http://localhost:8000/health/
```

### Stop the Platform

```bash
# Local mode
./scripts/stop.sh local

# Docker mode
./scripts/stop.sh docker
```

---

## API Reference

### Authentication

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/auth/login` | POST | Obtain JWT token | Public |
| `/auth/logout` | POST | Revoke session | Bearer |
| `/auth/sessions` | GET | List active sessions | ADMIN |

### Trading

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/execution/paper/start` | POST | Start paper trading | OPERATOR+ |
| `/execution/paper/stop` | POST | Stop paper trading | OPERATOR+ |
| `/orders/` | POST | Submit order | OPERATOR+ |
| `/orders/batch` | POST | Submit batch orders | OPERATOR+ |
| `/orders/history` | GET | Order history | ANALYST+ |
| `/positions/` | GET | Current positions | ANALYST+ |
| `/portfolio/summary` | GET | Portfolio summary | ANALYST+ |

### Decision Intelligence

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/decisions/` | GET | List decisions | ANALYST+ |
| `/decisions/{id}` | GET | Single decision | ANALYST+ |
| `/decisions/{id}/review` | POST | Mark reviewed | ANALYST+ |
| `/decisions/export/csv` | GET | Export CSV | ANALYST+ |
| `/decisions/summary/pipeline` | GET | Pipeline summary | ANALYST+ |

### System

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/health/` | GET | Health check | Public |
| `/status/` | GET | System status | Public |
| `/system/version` | GET | Version info | Public |
| `/system/state` | GET | System state | VIEWER+ |
| `/system/shutdown` | POST | Graceful shutdown | ADMIN |
| `/system/capabilities` | GET | Capability list | VIEWER+ |
| `/diagnostics/runtime` | GET | Runtime info | ANALYST+ |
| `/diagnostics/performance` | GET | Performance metrics | ANALYST+ |
| `/diagnostics/dependencies` | GET | Dependency list | ANALYST+ |
| `/diagnostics/config` | GET | Config dump | ADMIN |
| `/config/validate` | GET | Config validation | ADMIN |
| `/config/reload` | POST | Reload config | ADMIN |
| `/metrics/prometheus` | GET | Prometheus metrics | Public |
| `/audit/history` | GET | Audit trail | ANALYST+ |
| `/audit/export` | GET | Audit export CSV | ANALYST+ |

### WebSocket Feeds

| Endpoint | Description |
|----------|-------------|
| `/ws/decisions` | Real-time decision feed |
| `/ws/market` | Real-time market data |
| `/ws/system` | Real-time system events |

### Operator Dashboards

| URL | Description |
|-----|-------------|
| `/operator` | Operator console (auto-refresh 5s) |
| `/dashboard` | Decision review dashboard |

---

## Architecture

```
┌─────────────────────────────────────────┐
│  Operator Layer                          │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ /operator│ │/dashboard│ │/metrics │ │
│  │  HTML    │ │  HTML    │ │prom     │ │
│  └──────────┘ └──────────┘ └─────────┘ │
└────────────┬────────────────────────────┘
             │ HTTP / WebSocket
┌────────────▼────────────────────────────┐
│  FastAPI Platform API (14 routers)      │
│  Auth │ Health │ Status │ Config         │
│  Portfolio │ Positions │ Orders          │
│  Decisions │ Execution │ Metrics         │
│  Audit │ Diagnostics │ System           │
│  WebSocket                               │
└────────────┬────────────────────────────┘
             │
┌────────────▼────────────────────────────┐
│  Business Logic                         │
│  PaperBroker │ DecisionEngine │ Risk    │
└─────────────────────────────────────────┘
```

---

## Testing

```bash
# Run all tests
PYTHONPATH="src:$PYTHONPATH" python3 -m unittest discover -s tests

# Run specific suites
PYTHONPATH="src:$PYTHONPATH" python3 -m unittest discover -s tests/api
PYTHONPATH="src:$PYTHONPATH" python3 -m unittest discover -s tests/system
PYTHONPATH="src:$PYTHONPATH" python3 -m unittest discover -s tests/integration
```

---

## Security

- **JWT Authentication:** Per-process secret, 30-minute expiry
- **RBAC:** 4 roles (VIEWER, ANALYST, OPERATOR, ADMIN)
- **Rate Limiting:** 5 attempts per 60 seconds on auth endpoints
- **Audit Logging:** 100% coverage on state-changing endpoints
- **No Hardcoded Secrets:** All secrets via environment variables

---

## Runbooks

Complete operational procedures are available in `docs/runbooks/`:

| ID | Runbook | Audience |
|----|---------|----------|
| RB-001 | Initial Deployment | Engineering |
| RB-002 | System Startup | Operator |
| RB-003 | System Shutdown | Operator |
| RB-004 | Daily Operator Workflow | Operator |
| RB-005 | Paper Trading Session | Operator |
| RB-006 | Decision Review Workflow | Analyst |
| RB-007 | Backup Procedure | Operator |
| RB-008 | Restore Procedure | Engineering |
| RB-009 | Upgrade Procedure | Engineering |
| RB-010 | Failure Recovery | Engineering |
| RB-011 | Incident Response | Operations |
| RB-012 | Health Verification | Operator |
| RB-013 | Performance Verification | Engineering |

---

## Documentation

| Document | Description |
|----------|-------------|
| `README.md` | This file — quick start and overview |
| `CHANGELOG.md` | Version history and release notes |
| `RELEASE_NOTES.md` | Detailed release information |
| `DELIVERY_MAP.md` | Project structure and navigation guide |
| `docs/INSTALLATION.md` | Step-by-step installation guide |
| `docs/DEPLOYMENT.md` | Docker and Kubernetes deployment |
| `docs/ARCHITECTURE.md` | System architecture and data flow |
| `docs/CONFIGURATION.md` | Environment variables and settings |
| `docs/API.md` | Complete API reference |
| `docs/TROUBLESHOOTING.md` | Common issues and solutions |
| `docs/OPERATIONAL-SCENARIO-MATRIX.md` | 7 operator scenarios |
| `docs/OPERATOR-ACCEPTANCE-PACKAGE.md` | Operator acceptance procedures |
| `docs/UI-VERIFICATION-REPORT.md` | Frontend asset loading verification |
| `docs/BUILD-VERIFICATION-REPORT.md` | Build failure root cause analysis |
| `docs/FINAL-ENGINEERING-CERTIFICATION-REPORT.md` | Final engineering closure certification |
| `docs/runbooks/` | 13 operational runbooks |
| `deployment/README.md` | Kubernetes deployment guide |

---

## License

MIT License — see `pyproject.toml` for details.

---

*DATS Beta v1.0 — 2026-08-20 — Production Release Candidate*
