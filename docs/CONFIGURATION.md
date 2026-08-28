# DATS Configuration Guide

**Version:** 1.0.0-beta  
**Last Updated:** 2026-08-08  
**Audience:** Platform Engineers, DevOps, SRE

---

## Table of Contents

1. [Configuration Overview](#configuration-overview)
2. [Environment Variables Reference](#environment-variables-reference)
3. [Production vs Development Settings](#production-vs-development-settings)
4. [Security Considerations](#security-considerations)
5. [Configuration Validation](#configuration-validation)
6. [Runtime Reload](#runtime-reload)

---

## Configuration Overview

DATS uses environment variables for all configuration. The application loads settings at startup via `pydantic-settings` with validation. No configuration files are read from disk except `.env` during local development.

### Configuration Sources (Priority Order)

1. **Environment variables** (highest priority)
2. **`.env` file** (development only)
3. **Default values in code** (lowest priority)

### File Locations

| File | Purpose | Environment |
|------|---------|-------------|
| `.env.example` | Template with all variables and defaults | Reference |
| `.env` | Local overrides (gitignored) | Development |
| `deployment/k8s/configmap.yaml` | Non-sensitive K8s config | Production |
| `deployment/k8s/secret.yaml` | Sensitive K8s config | Production |

---

## Environment Variables Reference

### Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `dats` | Application identifier |
| `APP_VERSION` | `1.0.0-beta` | Release version |
| `APP_DEBUG` | `false` | Enable debug mode (stack traces, reload) |
| `APP_ENV` | `local` | Environment label: `local`, `staging`, `production` |

### Database (PostgreSQL)

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_USER` | `dats` | Database user |
| `DB_PASSWORD` | `dats` | Database password |
| `DB_NAME` | `dats` | Database name |
| `DB_POOL_SIZE` | `10` | Connection pool size |
| `DB_MAX_OVERFLOW` | `20` | Max overflow connections |
| `DB_ECHO` | `false` | Log SQL queries (debug) |
| `DB_POOL_RECYCLE` | `3600` | Connection recycle timeout (seconds) |
| `DB_POOL_TIMEOUT` | `30` | Pool acquisition timeout (seconds) |
| `DB_SSL_MODE` | `prefer` | SSL mode: `disable`, `prefer`, `require`, `verify-full` |

**Connection string (used in K8s):**
```
postgresql://user:password@host:5432/dbname
```

### Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `0` | Redis database index |
| `REDIS_PASSWORD` | *(empty)* | Redis authentication password |
| `REDIS_DECODE_RESPONSES` | `true` | Decode responses as strings |
| `REDIS_SOCKET_TIMEOUT` | `5` | Socket timeout (seconds) |
| `REDIS_SOCKET_CONNECT_TIMEOUT` | `5` | Connection timeout (seconds) |
| `REDIS_HEALTH_CHECK_INTERVAL` | `30` | Health check interval (seconds) |
| `REDIS_MAX_CONNECTIONS` | *(empty)* | Max connection pool size |

### Kafka

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Comma-separated broker list |
| `KAFKA_CLIENT_ID` | `dats` | Client identifier |
| `KAFKA_GROUP_ID` | `dats-consumer-group` | Consumer group ID |
| `KAFKA_ACKS` | `all` | Producer acknowledgement level |
| `KAFKA_RETRIES` | `3` | Producer retry count |
| `KAFKA_RETRY_BACKOFF_MS` | `1000` | Retry backoff (milliseconds) |
| `KAFKA_REQUEST_TIMEOUT_MS` | `30000` | Request timeout (milliseconds) |
| `KAFKA_AUTO_OFFSET_RESET` | `earliest` | Offset reset policy |
| `KAFKA_ENABLE_AUTO_COMMIT` | `true` | Enable auto-commit |
| `KAFKA_MAX_POLL_RECORDS` | `500` | Max records per poll |
| `KAFKA_SESSION_TIMEOUT_MS` | `10000` | Consumer session timeout |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `LOG_FORMAT` | `json` | Log format: `json`, `text` |
| `LOG_INCLUDE_TRACEBACK` | `true` | Include tracebacks in error logs |
| `LOG_LOGGER_NAME` | `dats` | Root logger name |
| `LOG_HANDLERS` | `console` | Comma-separated handlers: `console`, `file` |

### Metrics (Prometheus)

| Variable | Default | Description |
|----------|---------|-------------|
| `METRICS_PORT` | `9090` | Prometheus scrape port |
| `METRICS_PREFIX` | `dats` | Metric name prefix |
| `METRICS_PATH` | `/metrics` | Scrape endpoint path |
| `METRICS_ENABLED` | `true` | Enable metrics collection |

### Security (JWT)

| Variable | Default | Description |
|----------|---------|-------------|
| `SECURITY_JWT_SECRET` | *(required)* | JWT signing secret (min 32 chars) |
| `SECURITY_TOKEN_EXPIRY_MINUTES` | `60` | Access token expiry (minutes) |
| `SECURITY_ALGORITHM` | `HS256` | JWT algorithm |
| `SECURITY_REFRESH_TOKEN_EXPIRY_DAYS` | `7` | Refresh token expiry (days) |

### Trading (Pilot Mode)

| Variable | Default | Description |
|----------|---------|-------------|
| `TRADING_PILOT_MIN_USD` | `1.0` | Minimum pilot trade size (USD) |
| `TRADING_PILOT_MAX_USD` | `2.0` | Maximum pilot trade size (USD) |
| `TRADING_SLIPPAGE_BPS` | `30` | Assumed slippage (basis points) |
| `TRADING_PRICE_IMPACT_BPS` | `20` | Assumed price impact (basis points) |
| `TRADING_MAX_OPEN_POSITIONS` | `10` | Maximum concurrent open positions |
| `TRADING_ENABLE_AUTO_TRADE` | `false` | Enable automated trading |
| `TRADING_PAPER_TRADING` | `true` | Use paper/simulated trading |

### Server (K8s ConfigMap Only)

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVER_HOST` | `0.0.0.0` | Bind address |
| `SERVER_PORT` | `8000` | Listen port |
| `STATIC_DIR` | `/app/src/api/static` | Static files path |
| `TUI_PATH` | `/app/tui/main.py` | TUI entry point |
| `ENABLE_METRICS` | `true` | Enable metrics endpoint |
| `ENABLE_CORS` | `true` | Enable CORS middleware |
| `ENABLE_SWAGGER` | `true` | Enable OpenAPI/Swagger UI |
| `TZ` | `UTC` | Application timezone |

### CORS

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ALLOW_ORIGINS` | *(empty)* | Comma-separated allowed origins |

When empty, defaults to `http://localhost:3000` and `http://localhost:8000`.

---

## Production vs Development Settings

### Development

```bash
APP_DEBUG=true
APP_ENV=local
LOG_LEVEL=DEBUG
LOG_FORMAT=text
DB_ECHO=true
METRICS_ENABLED=false
TRADING_PAPER_TRADING=true
ENABLE_SWAGGER=true
```

Characteristics:
- Verbose logging to console
- SQL query echo enabled
- Swagger UI available at `/docs`
- Paper trading enforced
- Fast error pages with stack traces

### Staging

```bash
APP_DEBUG=false
APP_ENV=staging
LOG_LEVEL=INFO
LOG_FORMAT=json
DB_ECHO=false
METRICS_ENABLED=true
TRADING_PAPER_TRADING=true
ENABLE_SWAGGER=true
```

Characteristics:
- JSON logging for log aggregation
- Metrics enabled for monitoring
- Paper trading enforced
- Swagger UI available (internal use)

### Production

```bash
APP_DEBUG=false
APP_ENV=production
LOG_LEVEL=WARN
LOG_FORMAT=json
DB_ECHO=false
DB_SSL_MODE=require
METRICS_ENABLED=true
TRADING_PAPER_TRADING=true
ENABLE_SWAGGER=false
SECURITY_TOKEN_EXPIRY_MINUTES=30
```

Characteristics:
- Minimal logging (WARN+)
- JSON format for structured log ingestion
- TLS required for database connections
- Swagger UI disabled
- Shorter token expiry
- All external credentials use production endpoints

---

## Security Considerations

### Secrets Management

| Secret | Location | Notes |
|--------|----------|-------|
| `SECURITY_JWT_SECRET` | K8s Secret / Vault | Rotate on any security incident; min 32 random chars |
| `DB_PASSWORD` | K8s Secret / Vault | Use unique per-environment password |
| `REDIS_PASSWORD` | K8s Secret / Vault | Enable if Redis is network-accessible |
| `BROKER_API_SECRET` | K8s Secret / Vault | Rotate quarterly or on compromise |
| `OPENAI_API_KEY` | K8s Secret / Vault | Monitor usage for anomalous spend |

### Hardcoded Defaults to Override

The following values use placeholder defaults and **must** be changed in production:

```
SECURITY_JWT_SECRET=change-me-in-production-use-strong-secret-min-32-chars
DB_PASSWORD=dats
```

### SSL/TLS Configuration

| `DB_SSL_MODE` | Use Case |
|---------------|----------|
| `disable` | Local development only |
| `prefer` | Trusted networks, staging |
| `require` | Production (TLS enforced) |
| `verify-full` | Production (TLS + hostname verification) |

### Container Security

The Dockerfile enforces:
- Non-root execution (`USER dats`, UID mapped)
- Minimal runtime image (python:3.12-slim)
- No build tools in final image
- Health checks on the application endpoint

---

## Configuration Validation

Validate configuration before starting the application:

```bash
# Start the application and check config endpoint
curl http://localhost:8000/config/validate
```

Expected response:
```json
{
  "valid": true,
  "environment": "production",
  "checks": {
    "database": "connected",
    "redis": "connected",
    "jwt_secret": "configured"
  }
}
```

Invalid configuration will produce:
```json
{
  "valid": false,
  "errors": [
    "SECURITY_JWT_SECRET must be at least 32 characters",
    "DB_HOST is unreachable"
  ]
}
```

### Startup Validation

The bootstrap process (`system/bootstrap.py`) validates critical configuration before starting services. Missing required secrets will cause the container to exit with a clear error message.

---

## Runtime Reload

Configuration loaded at startup is cached in application state. To reload without restart:

```bash
# Admin only — requires ADMIN role
curl -X POST http://localhost:8000/config/reload \
  -H "Authorization: Bearer <admin-token>"
```

**Note:** Not all configuration supports runtime reload. Database connections, JWT secrets, and port bindings require a restart. The reload endpoint updates feature flags and logging levels only.

---

*DATS Beta v1.0 — Engineering Documentation*
