# DATS Deployment Guide

**Version:** 1.0.0-beta  
**Last Updated:** 2026-08-08  
**Audience:** Platform Engineers, DevOps, SRE

---

## Table of Contents

1. [Deployment Options](#deployment-options)
2. [Docker Compose Deployment](#docker-compose-deployment)
3. [Kubernetes Deployment](#kubernetes-deployment)
4. [Environment-Specific Configuration](#environment-specific-configuration)
5. [Health Checks](#health-checks)
6. [Troubleshooting Deployment](#troubleshooting-deployment)

---

## Deployment Options

| Method | Best For | Complexity | HA Support |
|--------|----------|------------|------------|
| Docker Compose | Development, staging, single-node production | Low | No |
| Kubernetes | Production, multi-region, auto-scaling | Medium | Yes |
| Local (bare metal) | Development, debugging | Low | No |

---

## Docker Compose Deployment

### Overview

The included `docker-compose.yml` orchestrates three services:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    dats     │────▶│  postgres   │     │    redis    │
│  (app:8000) │     │  (db:5432)  │◄────│  (cache)    │
└─────────────┘     └─────────────┘     └─────────────┘
```

### Quick Deploy

```bash
# From project root
./scripts/start.sh docker
```

This script:
1. Builds the Docker image from the multi-stage `Dockerfile`
2. Starts `dats`, `db`, and `redis` services
3. Waits for the health endpoint to return HTTP 200
4. Prints access URLs

### Manual Deploy

```bash
# Build and start in detached mode
docker-compose up -d --build

# Verify services
docker-compose ps

# View logs
docker-compose logs -f dats
```

### Docker Compose Services

| Service | Image | Ports | Restart |
|---------|-------|-------|---------|
| dats | Build from Dockerfile | 8000 | unless-stopped |
| db | postgres:16-alpine | 5432 | unless-stopped |
| redis | redis:7-alpine | 6379 | unless-stopped |

### Docker Compose Volumes

| Volume | Container Path | Purpose |
|--------|---------------|---------|
| postgres_data | /var/lib/postgresql/data | Persistent database storage |
| redis_data | /data | Persistent cache data |
| ./data | /app/data | Application data, logs, exports |

### Production Hardening (Docker Compose)

1. **Use external secrets management:**
   ```yaml
   environment:
     - DB_PASSWORD_FILE=/run/secrets/db_password
   secrets:
     - db_password
   ```

2. **Restrict port exposure:**
   Remove `ports` from `db` and `redis` services; use internal networking only.

3. **Enable resource limits:**
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '2.0'
         memory: 2G
   ```

4. **Use a reverse proxy** (nginx, Traefik) for TLS termination.

---

## Kubernetes Deployment

### Prerequisites

| Component | Version | Purpose |
|-----------|---------|---------|
| kubectl | 1.28+ | Cluster interaction |
| Kubernetes | 1.28+ | Container orchestration |
| Ingress Controller | Any | External traffic routing |

### Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Ingress / LB                      │
│              (TLS termination)                      │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│              Service (ClusterIP)                    │
│              Port: 8000                             │
└──────────────┬──────────────────────────────────────┘
               │
    ┌──────────┴──────────┐
    ▼                     ▼
┌─────────────┐     ┌─────────────┐
│  Pod 1      │     │  Pod 2      │
│  (api:8000) │     │  (api:8000) │
└─────────────┘     └─────────────┘
    │                     │
    └──────────┬──────────┘
               ▼
┌───────────────────────────────────────────────────┐
│  External PostgreSQL    │  External Redis         │
│  (RDS / Cloud SQL)      │  (ElastiCache / MemoryDB)│
└───────────────────────────────────────────────────┘
```

### Deploy Script

Use the provided deployment script for a fully automated installation:

```bash
bash deployment/scripts/deploy-k8s.sh
```

This script applies manifests in dependency order:
1. `namespace.yaml` — Creates `dats-beta-candidate` namespace
2. `configmap.yaml` — Non-sensitive configuration
3. `secret.yaml` — Sensitive credentials (⚠️ EDIT BEFORE APPLYING)
4. `deployment.yaml` — Application workload (2 replicas)
5. `service.yaml` — ClusterIP service
6. `ingress.yaml` — External routing (template — customize first)
7. `hpa.yaml` — Horizontal Pod Autoscaler

### Manual Manifest Application

```bash
# 1. Edit secrets FIRST
code deployment/k8s/secret.yaml

# 2. Apply in order
kubectl apply -f deployment/k8s/namespace.yaml
kubectl apply -f deployment/k8s/configmap.yaml
kubectl apply -f deployment/k8s/secret.yaml
kubectl apply -f deployment/k8s/deployment.yaml
kubectl apply -f deployment/k8s/service.yaml
kubectl apply -f deployment/k8s/ingress.yaml
kubectl apply -f deployment/k8s/hpa.yaml
```

### Secret Configuration

Before deploying, update `deployment/k8s/secret.yaml` with base64-encoded values:

```bash
# Encode secrets
echo -n 'your-db-password' | base64
echo -n 'your-jwt-secret' | base64
echo -n 'your-openai-key' | base64
```

| Secret Key | Description | Required |
|------------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `REDIS_URL` | Redis connection string | Yes |
| `SECRET_KEY` | JWT signing key (min 32 chars) | Yes |
| `MARKET_DATA_API_KEY` | External market data provider | No |
| `BROKER_API_KEY` / `BROKER_API_SECRET` | Exchange credentials | No |
| `OPENAI_API_KEY` | LLM provider key | No |

### Probes

The deployment configures three probe types:

| Probe | Path | Purpose | Timing |
|-------|------|---------|--------|
| Liveness | `/health` | Restart container if dead | initial: 30s, period: 10s |
| Readiness | `/health/ready` | Remove from service endpoints | initial: 10s, period: 5s |
| Startup | `/health` | Allow slow-start before liveness | initial: 10s, max: 60s |

### Resource Limits

Default resource configuration per pod:

| Resource | Request | Limit |
|----------|---------|-------|
| CPU | 250m | 1000m |
| Memory | 512Mi | 2Gi |

Adjust based on observed usage via Prometheus metrics.

### Horizontal Pod Autoscaler

Default HPA configuration:

| Metric | Target | Range |
|--------|--------|-------|
| CPU | 70% average utilization | 2–10 replicas |
| Memory | 80% average utilization | 2–10 replicas |

Scale-down stabilization: 300 seconds (prevents flapping).

### Rollback

Use the provided rollback script:

```bash
# View history
bash deployment/scripts/rollback.sh --history

# Rollback to previous revision
bash deployment/scripts/rollback.sh

# Rollback to specific revision
bash deployment/scripts/rollback.sh --revision 3

# Dry run
bash deployment/scripts/rollback.sh --dry-run
```

Or use kubectl directly:

```bash
# Undo last rollout
kubectl rollout undo deployment/dats-beta-candidate -n dats-beta-candidate

# Undo to specific revision
kubectl rollout undo deployment/dats-beta-candidate -n dats-beta-candidate --to-revision=2

# View rollout history
kubectl rollout history deployment/dats-beta-candidate -n dats-beta-candidate
```

---

## Environment-Specific Configuration

### Development

```bash
# .env overrides for development
APP_DEBUG=true
APP_ENV=local
LOG_LEVEL=DEBUG
LOG_FORMAT=text
TRADING_PAPER_TRADING=true
METRICS_ENABLED=false
```

### Staging

```bash
# .env overrides for staging
APP_DEBUG=false
APP_ENV=staging
LOG_LEVEL=INFO
LOG_FORMAT=json
TRADING_PAPER_TRADING=true
METRICS_ENABLED=true
```

### Production

```bash
# .env overrides for production
APP_DEBUG=false
APP_ENV=production
LOG_LEVEL=WARN
LOG_FORMAT=json
TRADING_PAPER_TRADING=true
METRICS_ENABLED=true
DB_SSL_MODE=require
SECURITY_TOKEN_EXPIRY_MINUTES=30
```

Critical production checklist:

- [ ] `SECURITY_JWT_SECRET` is strong, random, and ≥32 characters
- [ ] `DB_PASSWORD` is unique and rotated regularly
- [ ] `DB_SSL_MODE` is set to `require` or `verify-full`
- [ ] Redis is password-protected (`REDIS_PASSWORD`)
- [ ] All external API keys use production credentials
- [ ] Paper trading is enabled (`TRADING_PAPER_TRADING=true`) until OAT sign-off
- [ ] TLS is terminated at the ingress/load balancer
- [ ] Container runs as non-root user
- [ ] Resource limits are configured

---

## Health Checks

### Kubernetes Probes

| Probe | Endpoint | Failure Action |
|-------|----------|----------------|
| Liveness | `GET /health` | Container restart |
| Readiness | `GET /health/ready` | Remove from service |
| Startup | `GET /health` | Delay other probes |

### Manual Verification

```bash
# Overall health
curl http://<host>:8000/health/

# Specific component
curl http://<host>:8000/health/database
curl http://<host>:8000/health/redis

# System status
curl http://<host>:8000/status/

# Config validation
curl http://<host>:8000/config/validate
```

### Prometheus Metrics

```bash
curl http://<host>:8000/metrics/prometheus
```

---

## Troubleshooting Deployment

| Symptom | Diagnosis | Resolution |
|---------|-----------|------------|
| Pods stuck in `Pending` | Insufficient resources or missing PVC | Check `kubectl describe pod`; verify node capacity |
| `ImagePullBackOff` | Image not found or registry auth failed | Verify image tag exists; check `imagePullSecrets` |
| `CrashLoopBackOff` | App crashes on startup | Check logs: `kubectl logs -n dats-beta-candidate deployment/dats-beta-candidate` |
| Readiness probe fails | Database/Redis unreachable | Verify secrets and network connectivity to dependencies |
| HPA not scaling | Missing metrics server | Install `metrics-server` in cluster |
| 502 Bad Gateway from Ingress | Service has no ready endpoints | Check pod readiness; verify service selector labels |
| High memory usage | Memory leak or insufficient limits | Profile with `/diagnostics/performance`; increase limits or investigate |
| JWT auth failures | Clock skew or wrong secret | Verify `SECURITY_JWT_SECRET` matches across replicas; check NTP sync |

### Diagnostic Commands

```bash
# Pod status
kubectl get pods -n dats-beta-candidate

# Pod logs
kubectl logs -n dats-beta-candidate -l app.kubernetes.io/name=dats-beta-candidate --tail=200 -f

# Previous container logs (after crash)
kubectl logs -n dats-beta-candidate <pod-name> --previous

# Describe resource
kubectl describe pod -n dats-beta-candidate <pod-name>
kubectl describe deployment -n dats-beta-candidate dats-beta-candidate

# Exec into running container
kubectl exec -n dats-beta-candidate -it <pod-name> -- /bin/sh

# Port-forward for local debugging
kubectl port-forward -n dats-beta-candidate svc/dats-beta-candidate 8000:8000
```

---

*DATS Beta v1.0 — Engineering Documentation*
