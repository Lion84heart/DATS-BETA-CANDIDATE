# DATS System Architecture

**Version:** 1.0.0-beta  
**Last Updated:** 2026-08-08  
**Audience:** Software Architects, Senior Engineers, Tech Leads

---

## Table of Contents

1. [High-Level Architecture](#high-level-architecture)
2. [Component Diagram](#component-diagram)
3. [Module Descriptions](#module-descriptions)
4. [Data Flow](#data-flow)
5. [Technology Stack](#technology-stack)
6. [Security Architecture](#security-architecture)

---

## High-Level Architecture

DATS is a layered, modular platform built around a FastAPI core. It separates concerns into distinct layers: presentation, API routing, business logic, infrastructure, and data access.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                            │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐               │
│  │ /operator    │ │ /dashboard   │ │ /static/*    │               │
│  │ HTML Console │ │ Review UI    │ │ SPA Assets   │               │
│  └──────────────┘ └──────────────┘ └──────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼ HTTP / WebSocket
┌─────────────────────────────────────────────────────────────────────┐
│                         API ROUTING LAYER                            │
│  FastAPI Application (14 Routers, 64 Routes)                        │
│                                                                      │
│  Auth │ Health │ Status │ Config │ Portfolio │ Positions │ Orders   │
│  Decisions │ Execution │ Metrics │ Audit │ Diagnostics │ System    │
│  WebSocket (/ws/decisions, /ws/market, /ws/system)                  │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       BUSINESS LOGIC LAYER                           │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ PaperBroker  │  │DecisionEngine│  │ Risk Manager │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  AI Agents   │  │    Market    │  │   Pipeline   │              │
│  │              │  │  Connectors  │  │              │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      INFRASTRUCTURE LAYER                            │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  PostgreSQL  │  │    Redis     │  │    Kafka     │              │
│  │  (SQLAlchemy │  │  (Cache,     │  │  (Streaming  │              │
│  │   + asyncpg) │  │   Sessions)  │  │   Events)    │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ Prometheus   │  │  structlog   │  │   Alembic    │              │
│  │  Metrics     │  │  (JSON Logs)  │  │  Migrations  │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Diagram

```
                         ┌─────────────────┐
                         │   External      │
                         │   Clients       │
                         │ (Trader, Ops)   │
                         └────────┬────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │ HTTP/REST         │ WebSocket         │ Prometheus
              ▼                   ▼                   ▼
    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
    │  FastAPI App    │  │  WS Router      │  │  Metrics        │
    │  (api/main.py)  │  │  (api/routers/  │  │  (/metrics/     │
    │                 │  │   websocket.py) │  │   prometheus)   │
    └────────┬────────┘  └─────────────────┘  └─────────────────┘
             │
             ▼
    ┌──────────────────────────────────────────────────────────┐
    │              Router Layer (14 Routers)                    │
    │  auth  health  status  config  portfolio  positions     │
    │  orders  decisions  execution  metrics  audit           │
    │  diagnostics  system  websocket                           │
    └──────────────────────────────────────────────────────────┘
             │
             ▼
    ┌──────────────────────────────────────────────────────────┐
    │              Service / Business Layer                     │
    │                                                           │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
    │  │  Bootstrap  │  │   Health    │  │    Auth     │     │
    │  │  (system/)  │  │  (observ.)  │  │  (security) │     │
    │  └─────────────┘  └─────────────┘  └─────────────┘     │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
    │  │   Trading   │  │ Intelligence│  │    Market   │     │
    │  │  (trading/) │  │(intelligence)│  │  (market/)  │     │
    │  └─────────────┘  └─────────────┘  └─────────────┘     │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
    │  │   Agents    │  │ Simulation  │  │     Data    │     │
    │  │  (agents/)  │  │(simulation) │  │   (data/)   │     │
    │  └─────────────┘  └─────────────┘  └─────────────┘     │
    └──────────────────────────────────────────────────────────┘
             │
             ▼
    ┌──────────────────────────────────────────────────────────┐
    │              Infrastructure Layer                         │
    │                                                           │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
    │  │   asyncpg   │  │   Redis     │  │  aiokafka   │     │
    │  │ (PostgreSQL)│  │   Client    │  │   Client    │     │
    │  └─────────────┘  └─────────────┘  └─────────────┘     │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
    │  │ SQLAlchemy  │  │  Alembic    │  │  Prometheus │     │
    │  │   ORM       │  │ Migrations  │  │   Client    │     │
    │  └─────────────┘  └─────────────┘  └─────────────┘     │
    └──────────────────────────────────────────────────────────┘
```

---

## Module Descriptions

### `src/api/` — Web Layer

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `api/main.py` | FastAPI application factory, lifespan management | `app`, `lifespan` |
| `api/routers/` | 14 API route modules | `auth`, `health`, `orders`, `decisions`, etc. |
| `api/auth.py` | JWT authentication, session management | `authenticate_user`, `create_access_token` |
| `api/dependencies.py` | FastAPI dependency injection | `get_component` |
| `api/static/` | Static HTML/JS/CSS assets | `index.html`, `operator.html`, `terminal.html` |

### `src/trading/` — Trading Engine

| Module | Purpose |
|--------|---------|
| `trading/execution/` | Order execution, paper broker |
| `trading/risk/` | Risk metrics, position limits, exposure tracking |
| `trading/strategies/` | Trading strategy implementations |

### `src/intelligence/` — Decision Intelligence

| Module | Purpose |
|--------|---------|
| `intelligence/decisions.py` | Decision record store, querying, export |
| `intelligence/pipeline.py` | Decision processing pipeline |

### `src/agents/` — AI Agent Framework

| Module | Purpose |
|--------|---------|
| `agents/` | Agent orchestration, LLM integration, reasoning |

### `src/market/` — Market Data

| Module | Purpose |
|--------|---------|
| `market/connectors/` | External market data provider integrations |

### `src/security/` — Security Layer

| Module | Purpose |
|--------|---------|
| `security/` | JWT handling, RBAC enforcement, rate limiting, audit logging |

### `src/observability/` — Observability

| Module | Purpose |
|--------|---------|
| `observability/health.py` | Health check framework |
| `observability/metrics.py` | Prometheus metrics collection |
| `observability/logging.py` | Structured logging configuration |

### `src/system/` — System Framework

| Module | Purpose |
|--------|---------|
| `system/bootstrap.py` | Application bootstrap, dependency registry |
| `system/config_loader.py` | Environment-based configuration loading |
| `system/lifecycle.py` | Component lifecycle management (start/stop) |

### `src/infra/` — Infrastructure

| Module | Purpose |
|--------|---------|
| `infra/` | Database connection pools, Redis clients, Kafka producers |

### `src/simulation/` — Simulation

| Module | Purpose |
|--------|---------|
| `simulation/` | Paper trading environment, backtesting engine |

### `src/data/` — Data Layer

| Module | Purpose |
|--------|---------|
| `data/` | Feature store, data quality validation |

---

## Data Flow

### 1. Order Submission Flow

```
Operator ──▶ POST /orders ──▶ Auth Middleware ──▶ Rate Limit
                                    │
                                    ▼
                            Order Validation
                                    │
                                    ▼
                            Risk Check (exposure, limits)
                                    │
                                    ▼
                            PaperBroker Execution
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
            PostgreSQL (persist)          Redis (cache state)
                    │                               │
                    ▼                               ▼
            Audit Log Entry           WebSocket Broadcast
            (/audit/history)          (/ws/market)
```

### 2. Decision Intelligence Flow

```
Market Data ──▶ AI Agents ──▶ DecisionEngine
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            DecisionStore     Pipeline         WebSocket
            (PostgreSQL)      Processing       (/ws/decisions)
                                    │
                                    ▼
                            Operator Review
                            (/dashboard)
```

### 3. Authentication Flow

```
Client ──▶ POST /auth/login ──▶ RateLimiter (5/min/IP)
                                    │
                                    ▼
                            Credential Validation
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
            JWT Access Token              Session Record
            (30 min expiry)               (Redis + PostgreSQL)
                    │
                    ▼
            Bearer Authorization
            (subsequent requests)
```

---

## Technology Stack

### Core Framework

| Technology | Version | Role |
|------------|---------|------|
| Python | 3.12+ | Runtime language |
| FastAPI | 0.110+ | Web framework, ASGI |
| Uvicorn | 0.29+ | ASGI server |
| Pydantic | 2.7+ | Data validation, settings |

### Data & Storage

| Technology | Version | Role |
|------------|---------|------|
| PostgreSQL | 16+ | Primary database |
| SQLAlchemy | 2.0+ | ORM, async queries |
| asyncpg | 0.29+ | Async PostgreSQL driver |
| Redis | 7+ | Cache, sessions, rate limiting |
| Alembic | 1.13+ | Database migrations |

### Messaging & Streaming

| Technology | Version | Role |
|------------|---------|------|
| aiokafka | 0.10+ | Async Kafka client |
| WebSocket | native (FastAPI) | Real-time client feeds |

### Observability

| Technology | Version | Role |
|------------|---------|------|
| structlog | 24.1+ | Structured logging |
| prometheus-client | 0.20+ | Metrics exposition |
| python-json-logger | 2.0+ | JSON log formatting |

### Data Science

| Technology | Version | Role |
|------------|---------|------|
| pandas | 2.2+ | Data manipulation |
| numpy | 1.26+ | Numerical computing |
| scipy | 1.12+ | Statistical analysis |

### Security

| Technology | Version | Role |
|------------|---------|------|
| python-jose | 3.3+ | JWT encoding/decoding |
| cryptography | bundled | Cryptographic primitives |

### UI

| Technology | Version | Role |
|------------|---------|------|
| Textual | 0.50+ | Terminal User Interface (TUI) |
| Vanilla JS/HTML | — | Browser dashboards |

---

## Security Architecture

### Authentication

- **Mechanism:** JWT Bearer tokens (HS256)
- **Expiry:** 30 minutes (configurable)
- **Refresh:** 7-day refresh tokens
- **Secret:** Per-environment `SECURITY_JWT_SECRET`

### Authorization (RBAC)

| Role | Permissions |
|------|-------------|
| `VIEWER` | Read system state, capabilities |
| `ANALYST` | View decisions, positions, orders, diagnostics |
| `OPERATOR` | Submit orders, start/stop paper trading |
| `ADMIN` | Config reload, shutdown, session management, audit |

### Rate Limiting

| Endpoint | Limit | Window |
|----------|-------|--------|
| `/auth/login` | 5 attempts | 60 seconds per IP |

### Audit Logging

- 100% coverage on state-changing endpoints
- Captures: user, action, resource, timestamp, IP, user-agent
- Stored in PostgreSQL; accessible via `/audit/history`

### Network Security

| Layer | Control |
|-------|---------|
| Container | Runs as non-root (`dats` user, UID 1000) |
| Kubernetes | `runAsNonRoot: true`, `allowPrivilegeEscalation: false` |
| Ingress | TLS termination, optional rate limiting |
| CORS | Restricted to configured origins |

---

*DATS Beta v1.0 — Engineering Documentation*
