# DATS Troubleshooting Guide

**Version:** 1.0.0-beta  
**Last Updated:** 2026-08-08  
**Audience:** Operations, SRE, Platform Engineers

---

## Table of Contents

1. [Common Issues and Solutions](#common-issues-and-solutions)
2. [Log Locations](#log-locations)
3. [Health Check Interpretation](#health-check-interpretation)
4. [Diagnostic Endpoints](#diagnostic-endpoints)
5. [Recovery Procedures](#recovery-procedures)
6. [Emergency Contacts and Escalation](#emergency-contacts-and-escalation)

---

## Common Issues and Solutions

### Startup Failures

#### Symptom: Application fails to start, container exits immediately

**Docker Compose:**
```bash
docker-compose logs dats
```

**Kubernetes:**
```bash
kubectl logs -n dats-beta-candidate deployment/dats-beta-candidate
```

**Common Causes:**

| Error Message | Cause | Resolution |
|---------------|-------|------------|
| `Bootstrap failed: [DB_CONNECTION_ERROR]` | PostgreSQL unreachable | Verify `DB_HOST`, `DB_PORT`, credentials; check network connectivity |
| `Bootstrap failed: [REDIS_CONNECTION_ERROR]` | Redis unreachable | Verify `REDIS_HOST`, `REDIS_PORT`; check Redis container/pod |
| `SECRET_KEY must be at least 32 characters` | Weak JWT secret | Set `SECURITY_JWT_SECRET` to ≥32 random characters |
| `ModuleNotFoundError: api` | PYTHONPATH issue | Ensure `PYTHONPATH=/app/src` (Docker) or `PYTHONPATH=src` (local) |
| `Address already in use` | Port 8000 conflict | Kill existing process or change `SERVER_PORT` |

---

### Authentication Issues

#### Symptom: `401 Unauthorized` on all protected endpoints

1. **Verify token acquisition:**
   ```bash
   curl -X POST http://localhost:8000/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"admin"}'
   ```

2. **Check token expiry:**
   Decode the JWT payload (Base64 middle section). Verify `exp` timestamp.

3. **Verify secret consistency:**
   Ensure `SECURITY_JWT_SECRET` matches across all replicas.

4. **Check clock skew:**
   JWT validation is sensitive to clock drift. Verify NTP sync on all nodes.

#### Symptom: `403 Forbidden`

The user is authenticated but lacks permission. Check RBAC assignment:

| Required Role | Endpoints |
|---------------|-----------|
| `VIEWER` | `/system/state`, `/system/capabilities` |
| `ANALYST` | `/decisions/*`, `/positions`, `/orders/history`, `/diagnostics/*` |
| `OPERATOR` | `/orders`, `/orders/batch`, `/execution/paper/*` |
| `ADMIN` | `/auth/sessions`, `/system/shutdown`, `/config/reload`, `/diagnostics/config` |

---

### Database Issues

#### Symptom: Slow queries or connection pool exhaustion

```bash
# Check active connections
curl http://localhost:8000/diagnostics/runtime
```

**Resolution:**
1. Increase `DB_POOL_SIZE` and `DB_MAX_OVERFLOW`
2. Review long-running queries via PostgreSQL `pg_stat_activity`
3. Enable `DB_ECHO=true` temporarily to log all SQL

#### Symptom: Connection refused to PostgreSQL

**Docker Compose:**
```bash
docker-compose ps db
docker-compose exec db pg_isready -U dats -d dats
```

**Kubernetes:**
Verify external PostgreSQL endpoint is reachable from cluster:
```bash
kubectl exec -n dats-beta-candidate -it <pod-name> -- sh -c "python -c \"import asyncpg; ...\""
```

---

### Memory and Performance

#### Symptom: High memory usage or OOMKilled

```bash
# Check current metrics
curl http://localhost:8000/diagnostics/performance
```

**Kubernetes-specific:**
```bash
kubectl top pod -n dats-beta-candidate
kubectl describe pod -n dats-beta-candidate <pod-name>
```

**Resolution:**
1. Increase memory limit in `deployment.yaml`
2. Check for memory leaks in custom strategies
3. Reduce `KAFKA_MAX_POLL_RECORDS` if message backlog accumulates
4. Enable garbage collection profiling in `/diagnostics/performance`

#### Symptom: High latency (p95 > 50ms)

```bash
# Performance diagnostics
curl http://localhost:8000/diagnostics/performance
```

Check for:
- Database connection pool saturation
- Redis latency spikes
- Blocking I/O in custom code
- Insufficient CPU allocation

---

### WebSocket Issues

#### Symptom: WebSocket connections drop immediately

1. **Authentication:** Verify token is passed as query parameter: `?token=<jwt>`
2. **Ingress configuration:** Ensure proxy supports WebSocket upgrade
   ```yaml
   nginx.ingress.kubernetes.io/proxy-read-timeout: "60"
   nginx.ingress.kubernetes.io/proxy-send-timeout: "60"
   ```
3. **Load balancer:** Ensure sticky sessions are NOT required (stateless design)

---

## Log Locations

### Local Development

| Location | Description |
|----------|-------------|
| `data/logs/api.log` | Application stdout (when started via `start.sh local`) |
| Terminal stdout | Real-time logs when running `uvicorn` directly |

### Docker Compose

```bash
# Application logs
docker-compose logs -f dats

# Database logs
docker-compose logs -f db

# Redis logs
docker-compose logs -f redis
```

### Kubernetes

```bash
# Current logs
kubectl logs -n dats-beta-candidate -l app.kubernetes.io/name=dats-beta-candidate --tail=500 -f

# Previous container logs (after crash/restart)
kubectl logs -n dats-beta-candidate <pod-name> --previous

# All pods in namespace
kubectl logs -n dats-beta-candidate --all-containers --prefix
```

### Log Format

Production logs use structured JSON:

```json
{
  "timestamp": "2026-08-08T12:00:00.000Z",
  "level": "INFO",
  "logger": "dats.api.auth",
  "message": "User authenticated",
  "event": "LOGIN",
  "user": "admin",
  "ip_address": "10.0.0.1",
  "session_id": "abc123"
}
```

---

## Health Check Interpretation

### Endpoint: `GET /health/`

Returns overall system health with per-component status.

#### Response Format

```json
{
  "status": 3,
  "checks": {
    "database": {
      "healthy": true,
      "message": "connected"
    },
    "redis": {
      "healthy": true,
      "message": "connected"
    }
  },
  "timestamp": "2026-08-08T12:00:00Z"
}
```

#### Status Codes

| Status Value | Meaning | Action |
|--------------|---------|--------|
| `3` | All checks healthy | None |
| `2` | Degraded (non-critical component failing) | Monitor; investigate soon |
| `1` | Critical component failing | Investigate immediately |
| `0` | System down | PagerDuty / on-call |

### Endpoint: `GET /health/{check_name}`

Get detailed status for a specific component:

```bash
curl http://localhost:8000/health/database
curl http://localhost:8000/health/redis
```

### Kubernetes Probes

| Probe | Path | Failure Handling |
|-------|------|-----------------|
| Liveness | `/health` | Container restart |
| Readiness | `/health/ready` | Remove from service endpoints |
| Startup | `/health` | Delay liveness/readiness |

**Note:** The deployment manifest uses `/health` for liveness and startup, and `/health/ready` for readiness. Ensure the readiness endpoint exists; if not, fallback to `/health`.

---

## Diagnostic Endpoints

### Runtime Information

```bash
curl http://localhost:8000/diagnostics/runtime
```

Returns Python version, memory usage, thread count, asyncio task count, and loaded modules.

### Performance Metrics

```bash
curl http://localhost:8000/diagnostics/performance
```

Returns request latency histograms, throughput counters, and active connection counts.

### Dependency Check

```bash
curl http://localhost:8000/diagnostics/dependencies
```

Returns versions of all installed packages and their health status.

### Config Dump (Admin Only)

```bash
curl http://localhost:8000/diagnostics/config \
  -H "Authorization: Bearer <admin-token>"
```

Returns current configuration values (secrets are masked).

---

## Recovery Procedures

### Procedure 1: Graceful Restart

**Scenario:** Configuration updated, minor patch applied.

```bash
# Kubernetes rolling restart
kubectl rollout restart deployment/dats-beta-candidate -n dats-beta-candidate

# Docker Compose
./scripts/stop.sh docker
./scripts/start.sh docker

# Local
kill $(cat .dats.pid)
./scripts/start.sh local
```

### Procedure 2: Database Connection Recovery

**Scenario:** Database connectivity lost, connection pool exhausted.

```bash
# 1. Verify database is reachable
./scripts/health_check.sh

# 2. If database is down, restart database service
# Docker Compose:
docker-compose restart db

# 3. Restart application to re-establish connections
# Docker Compose:
docker-compose restart dats

# Kubernetes:
kubectl rollout restart deployment/dats-beta-candidate -n dats-beta-candidate
```

### Procedure 3: JWT Secret Rotation

**Scenario:** JWT secret compromised or rotation required.

```bash
# 1. Update SECRET_KEY in environment
# 2. Rolling restart to pick up new secret
kubectl rollout restart deployment/dats-beta-candidate -n dats-beta-candidate

# 3. All existing sessions will be invalidated
# 4. Users must re-authenticate
```

### Procedure 4: Pod Eviction / OOM Recovery

**Scenario:** Pod killed due to memory limit or node pressure.

```bash
# 1. Check eviction reason
kubectl describe pod -n dats-beta-candidate <pod-name>

# 2. If OOMKilled, increase memory limit
# Edit deployment/k8s/deployment.yaml
# Change: limits.memory to a higher value

# 3. Re-apply deployment
kubectl apply -f deployment/k8s/deployment.yaml

# 4. Monitor
kubectl top pod -n dats-beta-candidate
```

### Procedure 5: Full System Shutdown and Restart

**Scenario:** Complete platform restart required.

```bash
# Kubernetes
kubectl scale deployment dats-beta-candidate -n dats-beta-candidate --replicas=0
# ... perform maintenance ...
kubectl scale deployment dats-beta-candidate -n dats-beta-candidate --replicas=2

# Docker Compose
./scripts/stop.sh docker
# ... perform maintenance ...
./scripts/start.sh docker

# Local
./scripts/stop.sh local
# ... perform maintenance ...
./scripts/start.sh local
```

### Procedure 6: Rollback After Bad Deployment

```bash
# Kubernetes
bash deployment/scripts/rollback.sh

# Or manual
kubectl rollout undo deployment/dats-beta-candidate -n dats-beta-candidate
```

---

## Emergency Contacts and Escalation

| Severity | Condition | Response Time | Action |
|----------|-----------|---------------|--------|
| P0 — Critical | Trading halted, data loss, security breach | 15 min | Page on-call; engage engineering lead |
| P1 — High | Major feature degraded, performance severely impacted | 1 hour | Create incident; assign engineer |
| P2 — Medium | Non-critical feature unavailable | 4 hours | Add to sprint; monitor |
| P3 — Low | Cosmetic issue, documentation gap | 2 days | Ticket for next cycle |

### Incident Response Checklist

- [ ] Acknowledge incident in Slack `#incidents`
- [ ] Create incident channel `#incident-YYYY-MM-DD-brief`
- [ ] Assign Incident Commander
- [ ] Document timeline in incident channel
- [ ] Post-mortem within 48 hours for P0/P1

---

*DATS Beta v1.0 — Engineering Documentation*
