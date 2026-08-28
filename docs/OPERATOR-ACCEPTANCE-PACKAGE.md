# Operator Acceptance Package — DATS Alpha v1.0

**Version:** 1.0  
**Date:** 2026-08-09  
**Project:** DATS — Institutional AI Trading Platform  
**Release:** Alpha v1.0  
**Audience:** Operators, Analysts, Operations Team  
**Status:** READY FOR OPERATIONAL ACCEPTANCE

---

## Welcome

This package contains everything an operator needs to deploy, run, and maintain the DATS Alpha v1.0 platform.

No developer assistance is required for day-to-day operations.

---

## Quick Reference Card

```
DATS Alpha v1.0 — Operator Quick Reference
====================================================

START:      bash scripts/start.sh local
STOP:       bash scripts/stop.sh local
HEALTH:     curl http://localhost:8000/health/
DASHBOARD:  http://localhost:8000/operator
METRICS:    http://localhost:8000/metrics/prometheus

LOGIN:      POST /auth/login  →  {access_token}
PAPER ON:   POST /execution/paper/start
PAPER OFF:  POST /execution/paper/stop
ORDERS:     GET  /orders/history
POSITIONS:  GET  /positions/
DECISIONS:  GET  /decisions/?limit=10
EXPORT:     GET  /decisions/export/csv

ROLES:      VIEWER < ANALYST < OPERATOR < ADMIN
```

---

## Role-Based Access

| Role | Can Do | Cannot Do |
|------|--------|-----------|
| **VIEWER** | View health, status, system state | Execute trades, modify config |
| **ANALYST** | View decisions, audit, portfolio, positions, diagnostics | Execute trades, system control |
| **OPERATOR** | All ANALYST functions + submit orders, start/stop paper trading | System shutdown, config reload |
| **ADMIN** | All functions including shutdown, config reload, session management | — |

---

## Daily Workflow (5 Minutes)

```bash
# 1. Start platform
bash scripts/start.sh local

# 2. Log in as operator
curl -X POST http://localhost:8000/auth/login   -H "Content-Type: application/json"   -d '{"username":"operator","password":"operator123"}'

# 3. Start paper trading
curl -X POST http://localhost:8000/execution/paper/start   -H "Authorization: Bearer $TOKEN"

# 4. Submit orders, review decisions, export data
#    (see RB-004: Daily Operator Workflow)

# 5. Stop paper trading
curl -X POST http://localhost:8000/execution/paper/stop   -H "Authorization: Bearer $TOKEN"

# 6. Log out
curl -X POST http://localhost:8000/auth/logout   -H "Authorization: Bearer $TOKEN"
```

---

## Runbook Index

| When You Need To... | See Runbook |
|---------------------|-------------|
| Deploy for the first time | RB-001: Initial Deployment |
| Start the platform | RB-002: System Startup |
| Stop the platform | RB-003: System Shutdown |
| Execute daily trading | RB-004: Daily Operator Workflow |
| Run a paper trading session | RB-005: Paper Trading Session |
| Review AI decisions | RB-006: Decision Review Workflow |
| Create a backup | RB-007: Backup Procedure |
| Restore from backup | RB-008: Restore Procedure |
| Upgrade to new version | RB-009: Upgrade Procedure |
| Recover from failure | RB-010: Failure Recovery |
| Respond to an incident | RB-011: Incident Response |
| Verify system health | RB-012: Health Verification |
| Verify performance | RB-013: Performance Verification |

---

## Health Check Commands

```bash
# Basic health
curl http://localhost:8000/health/
# Expected: {"status": "ok"}

# System state
curl http://localhost:8000/system/state
# Expected: {"status": "HEALTHY"}

# Version
curl http://localhost:8000/system/version
# Expected: {"version": "1.0.0-beta", ...}

# Diagnostics
curl -H "Authorization: Bearer $TOKEN"   http://localhost:8000/diagnostics/runtime
```

---

## Emergency Procedures

### Platform Won't Start
1. Check port 8000 is free: `lsof -i :8000`
2. Check logs: look at console output or `data/logs/`
3. Verify `.env` exists: `ls -la .env`
4. Run health verification: see RB-012
5. If still failing: see RB-010: Failure Recovery

### Paper Trading Stuck
1. Check if already running: `GET /execution/paper/status`
2. Stop and restart: `POST /execution/paper/stop` then `POST /execution/paper/start`
3. If unresponsive: see RB-010

### Forgot Admin Password
1. JWT secrets are per-process — restart the platform
2. New process generates new secret
3. Re-authenticate with valid credentials

---

## Support Escalation

| Issue Type | First Response | Escalate To |
|------------|---------------|-------------|
| Operator workflow question | RB-004, RB-005, RB-006 | Operations Lead |
| System won't start | RB-002, RB-010 | Engineering |
| Performance degradation | RB-013 | Engineering |
| Security concern | RB-011 | Security Team |
| Data loss | RB-008 | Engineering + Product |

---

## Acceptance Sign-Off

By signing below, the operations team confirms:

- [ ] All 13 runbooks have been reviewed
- [ ] RB-001 (Initial Deployment) executed successfully
- [ ] RB-012 (Health Verification) executed successfully
- [ ] RB-004 (Daily Operator Workflow) executed successfully
- [ ] RB-005 (Paper Trading Session) executed successfully
- [ ] RB-007 (Backup Procedure) executed successfully
- [ ] Incident response process is understood
- [ ] Escalation paths are known

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Operations Lead | | | |
| Lead Operator | | | |
| Lead Analyst | | | |

---

*Operator Acceptance Package version: 1.0*  
*Date: 2026-08-09*  
*Status: READY FOR OPERATIONAL ACCEPTANCE*
