# DATS-BETA-CANDIDATE Deployment Guide

This directory contains all Kubernetes manifests, shell scripts, and documentation required to deploy the **DATS-BETA-CANDIDATE** institutional AI trading platform.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Docker Compose Deployment](#docker-compose-deployment)
3. [Kubernetes Deployment](#kubernetes-deployment)
4. [Health Check Endpoints](#health-check-endpoints)
5. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Option A: Docker & Docker Compose (Recommended for local development)

- Docker Engine >= 24.0
- Docker Compose >= 2.20
- 4 GB RAM minimum, 8 GB recommended

### Option B: Kubernetes (Recommended for production)

- Kubernetes cluster >= 1.28
- kubectl CLI configured and authenticated
- Helm 3 (optional, for future Helm chart support)
- NGINX Ingress Controller or equivalent
- cert-manager (optional, for TLS automation)

### Option C: Local Python 3.12 (Development only)

- Python 3.12+
- pip / poetry / uv package manager
- Redis (for caching / pub-sub)
- PostgreSQL or SQLite (for persistence)

---

## Docker Compose Deployment

The project root contains a `docker-compose.yml` for quick local deployment.

```bash
# From the project root
cd /path/to/DATS-BETA-CANDIDATE

# Build and start all services
docker compose up --build -d

# View logs
docker compose logs -f app

# Stop all services
docker compose down
```

The FastAPI application will be available at `http://localhost:8000`.

---

## Kubernetes Deployment

### 1. Quick Deploy (One-Command)

Run the provided deployment script from the project root:

```bash
cd /path/to/DATS-BETA-CANDIDATE
bash deployment/scripts/deploy-k8s.sh
```

This script applies all manifests in the correct order:
1. Namespace
2. ConfigMap
3. Secret (template — see step 2 below)
4. Deployment
5. Service
6. Ingress (optional)
7. HorizontalPodAutoscaler

### 2. Configure Secrets (REQUIRED before first deploy)

The `secret.yaml` manifest contains placeholder values. **You must replace them with real secrets before deploying.**

```bash
# Edit the secret template and replace base64-encoded placeholders
# Then apply:
kubectl apply -f deployment/k8s/secret.yaml
```

To generate base64-encoded secrets:

```bash
echo -n 'your-secret-value' | base64
```

### 3. Verify Deployment

```bash
# Check pod status
kubectl get pods -n dats-beta-candidate

# Check service
kubectl get svc -n dats-beta-candidate

# Check logs
kubectl logs -n dats-beta-candidate -l app=dats-beta-candidate --tail=100 -f

# Port-forward for local access
kubectl port-forward -n dats-beta-candidate svc/dats-beta-candidate 8000:8000
```

### 4. Access the Application

- **Cluster internal**: `http://dats-beta-candidate.dats-beta-candidate.svc.cluster.local:8000`
- **Via port-forward**: `http://localhost:8000`
- **Via Ingress**: Configure `ingress.yaml` with your domain and apply.

### 5. Update / Rollback

```bash
# Update image tag in deployment.yaml, then apply
kubectl apply -f deployment/k8s/deployment.yaml

# Or use the rollback script
bash deployment/scripts/rollback.sh
```

---

## Health Check Endpoints

The FastAPI application exposes the following health endpoints on port 8000:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness probe — returns 200 if the app is running |
| `/health/ready` | GET | Readiness probe — returns 200 when ready to accept traffic |
| `/health/metrics` | GET | Prometheus-compatible metrics (if enabled) |

### Kubernetes Probe Configuration

- **Liveness Probe**: `GET /health` — restarts container on failure
- **Readiness Probe**: `GET /health/ready` — removes pod from service endpoints on failure
- **Startup Probe**: `GET /health` — allows slow-starting containers time to initialize

---

## Troubleshooting

### Pods stuck in `Pending`

```bash
kubectl describe pod -n dats-beta-candidate <pod-name>
```
Common causes: insufficient cluster resources, missing PersistentVolumeClaims, or unschedulable nodes.

### Pods stuck in `CrashLoopBackOff`

```bash
kubectl logs -n dats-beta-candidate <pod-name> --previous
```
Common causes: missing environment variables (check secrets), incorrect database connection string, or missing dependencies.

### Service not reachable

```bash
kubectl get endpoints -n dats-beta-candidate svc/dats-beta-candidate
```
If endpoints are empty, the readiness probe is likely failing. Check pod logs.

### Ingress not working

1. Ensure an Ingress Controller (e.g., NGINX) is installed:
   ```bash
   kubectl get pods -n ingress-nginx
   ```
2. Verify DNS points to the Ingress Controller load balancer IP.
3. Check Ingress logs:
   ```bash
   kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx
   ```

### High Memory / CPU Usage

Check HPA status:

```bash
kubectl get hpa -n dats-beta-candidate
```

If pods are throttled, increase resource limits in `deployment.yaml` or scale the cluster.

### Full Reset

```bash
kubectl delete namespace dats-beta-candidate
bash deployment/scripts/deploy-k8s.sh
```

---

## File Structure

```
deployment/
├── README.md                      # This file
├── k8s/
│   ├── namespace.yaml             # Namespace definition
│   ├── configmap.yaml             # Non-sensitive configuration
│   ├── secret.yaml                # Sensitive configuration (template)
│   ├── deployment.yaml            # Application deployment
│   ├── service.yaml               # ClusterIP service
│   ├── ingress.yaml               # Ingress rules (template)
│   └── hpa.yaml                   # HorizontalPodAutoscaler
└── scripts/
    ├── deploy-k8s.sh              # One-command K8s deploy
    └── rollback.sh                # Rollback utility
```

---

## Support

For issues or questions, refer to the project documentation or contact the platform engineering team.
