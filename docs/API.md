# DATS API Reference

**Version:** 1.0.0-beta  
**Last Updated:** 2026-08-08  
**Audience:** API Consumers, Frontend Engineers, Integrators

---

## Table of Contents

1. [Authentication](#authentication)
2. [Endpoint Categories](#endpoint-categories)
3. [Public Endpoints](#public-endpoints)
4. [Trading Endpoints](#trading-endpoints)
5. [Decision Intelligence Endpoints](#decision-intelligence-endpoints)
6. [System Endpoints](#system-endpoints)
7. [WebSocket Usage](#websocket-usage)
8. [Error Responses](#error-responses)
9. [Rate Limits](#rate-limits)

---

## Authentication

DATS uses JWT Bearer tokens for authentication. Tokens are obtained via the `/auth/login` endpoint and must be included in the `Authorization` header for protected endpoints.

### Login

```http
POST /auth/login
Content-Type: application/json
```

**Request Body:**
```json
{
  "username": "admin",
  "password": "admin"
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 1800,
  "role": "ADMIN"
}
```

**Rate Limit:** 5 attempts per 60 seconds per IP. Exceeding returns `429 Too Many Requests`.

### Using the Token

Include the token in the `Authorization` header for all protected requests:

```http
GET /orders/history
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### Logout

```http
POST /auth/logout
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "status": "logged_out"
}
```

### Get Current User

```http
GET /auth/me
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "username": "admin",
  "full_name": "Administrator",
  "email": "admin@dats.dev",
  "role": "ADMIN",
  "disabled": false
}
```

### List Active Sessions (Admin Only)

```http
GET /auth/sessions
Authorization: Bearer <admin-token>
```

---

## Endpoint Categories

| Category | Prefix | Auth Required |
|----------|--------|---------------|
| Authentication | `/auth` | Public (login), Bearer (others) |
| Health | `/health` | None |
| Status | `/status` | None |
| Portfolio | `/portfolio` | ANALYST+ |
| Positions | `/positions` | ANALYST+ |
| Orders | `/orders` | OPERATOR+ |
| Decisions | `/decisions` | ANALYST+ |
| Execution | `/execution` | OPERATOR+ |
| Metrics | `/metrics` | Public |
| Audit | `/audit` | ANALYST+ |
| Diagnostics | `/diagnostics` | ANALYST+ |
| System | `/system` | VIEWER+ |
| Config | `/config` | ADMIN |
| WebSocket | `/ws` | Token query param |

---

## Public Endpoints

### Health Check

```http
GET /health/
```

**Response (200):**
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

### System Status

```http
GET /status/
```

**Response (200):**
```json
{
  "state": "running",
  "uptime": 3600,
  "version": "1.0.0-beta"
}
```

### Version

```http
GET /system/version
```

**Response (200):**
```json
{
  "version": "1.0.0-beta",
  "name": "DATS"
}
```

### Prometheus Metrics

```http
GET /metrics/prometheus
```

Returns Prometheus-compatible metrics exposition.

### System Capabilities

```http
GET /system/capabilities
```

**Response (200):**
```json
{
  "capabilities": [
    "paper_trading",
    "decision_intelligence",
    "websocket_feeds",
    "metrics_export"
  ]
}
```

---

## Trading Endpoints

### Paper Trading Control

#### Start Paper Trading

```http
POST /execution/paper/start
Authorization: Bearer <operator-token>
```

**Response (200):**
```json
{
  "status": "started",
  "mode": "paper",
  "timestamp": "2026-08-08T12:00:00Z"
}
```

#### Stop Paper Trading

```http
POST /execution/paper/stop
Authorization: Bearer <operator-token>
```

**Response (200):**
```json
{
  "status": "stopped",
  "timestamp": "2026-08-08T12:00:00Z"
}
```

### Orders

#### Submit Order

```http
POST /orders/
Authorization: Bearer <operator-token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "symbol": "AAPL",
  "side": "buy",
  "quantity": 100,
  "order_type": "market",
  "time_in_force": "day"
}
```

**Response (200):**
```json
{
  "order_id": "ord-12345",
  "status": "filled",
  "symbol": "AAPL",
  "side": "buy",
  "quantity": 100,
  "filled_quantity": 100,
  "avg_price": 175.50,
  "timestamp": "2026-08-08T12:00:00Z"
}
```

#### Submit Batch Orders

```http
POST /orders/batch
Authorization: Bearer <operator-token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "orders": [
    {"symbol": "AAPL", "side": "buy", "quantity": 100},
    {"symbol": "GOOGL", "side": "sell", "quantity": 50}
  ]
}
```

#### Get Order History

```http
GET /orders/history
Authorization: Bearer <analyst-token>
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `symbol` | string | Filter by symbol |
| `status` | string | Filter by status: `filled`, `pending`, `cancelled` |
| `limit` | integer | Max records to return (default: 50) |
| `offset` | integer | Pagination offset |

**Response (200):**
```json
{
  "total": 150,
  "orders": [
    {
      "order_id": "ord-12345",
      "symbol": "AAPL",
      "side": "buy",
      "quantity": 100,
      "status": "filled",
      "timestamp": "2026-08-08T12:00:00Z"
    }
  ]
}
```

### Positions

#### Get Current Positions

```http
GET /positions/
Authorization: Bearer <analyst-token>
```

**Response (200):**
```json
{
  "positions": [
    {
      "symbol": "AAPL",
      "quantity": 100,
      "avg_entry_price": 175.50,
      "current_price": 178.00,
      "unrealized_pnl": 250.00,
      "timestamp": "2026-08-08T12:00:00Z"
    }
  ],
  "total_exposure": 17800.00
}
```

### Portfolio

#### Get Portfolio Summary

```http
GET /portfolio/summary
Authorization: Bearer <analyst-token>
```

**Response (200):**
```json
{
  "total_value": 100000.00,
  "cash_balance": 82200.00,
  "position_value": 17800.00,
  "unrealized_pnl": 250.00,
  "realized_pnl": 0.00,
  "positions_count": 1,
  "timestamp": "2026-08-08T12:00:00Z"
}
```

---

## Decision Intelligence Endpoints

### List Decisions

```http
GET /decisions/
Authorization: Bearer <analyst-token>
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | integer | Max records (default: 50) |
| `offset` | integer | Pagination offset |
| `reviewed` | boolean | Filter by review status |
| `symbol` | string | Filter by symbol |

**Response (200):**
```json
{
  "total": 320,
  "decisions": [
    {
      "id": "dec-789",
      "symbol": "AAPL",
      "action": "buy",
      "confidence": 0.87,
      "rationale": "Bullish technical breakout",
      "reviewed": false,
      "timestamp": "2026-08-08T12:00:00Z"
    }
  ]
}
```

### Get Single Decision

```http
GET /decisions/{id}
Authorization: Bearer <analyst-token>
```

### Mark Decision as Reviewed

```http
POST /decisions/{id}/review
Authorization: Bearer <analyst-token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "reviewer": "analyst1",
  "notes": "Approved — aligns with strategy",
  "approved": true
}
```

### Export Decisions to CSV

```http
GET /decisions/export/csv
Authorization: Bearer <analyst-token>
```

**Response:** `text/csv` attachment.

### Pipeline Summary

```http
GET /decisions/summary/pipeline
Authorization: Bearer <analyst-token>
```

**Response (200):**
```json
{
  "total_decisions": 320,
  "pending_review": 12,
  "approved": 280,
  "rejected": 28,
  "avg_confidence": 0.82,
  "last_decision_at": "2026-08-08T11:55:00Z"
}
```

---

## System Endpoints

### System State

```http
GET /system/state
Authorization: Bearer <viewer-token>
```

### Diagnostics

#### Runtime Information

```http
GET /diagnostics/runtime
Authorization: Bearer <analyst-token>
```

**Response (200):**
```json
{
  "python_version": "3.12.0",
  "platform": "Linux-6.5-x86_64",
  "memory_mb": 163.6,
  "threads": 8,
  "asyncio_tasks": 12,
  "uptime_seconds": 3600
}
```

#### Performance Metrics

```http
GET /diagnostics/performance
Authorization: Bearer <analyst-token>
```

#### Dependency List

```http
GET /diagnostics/dependencies
Authorization: Bearer <analyst-token>
```

### Audit

#### Get Audit History

```http
GET /audit/history
Authorization: Bearer <analyst-token>
```

**Response (200):**
```json
{
  "total": 1250,
  "events": [
    {
      "timestamp": "2026-08-08T12:00:00Z",
      "user": "operator1",
      "action": "ORDER_SUBMIT",
      "resource": "orders",
      "details": "symbol=AAPL,side=buy,qty=100",
      "ip_address": "10.0.0.1"
    }
  ]
}
```

#### Export Audit CSV

```http
GET /audit/export
Authorization: Bearer <analyst-token>
```

### Configuration (Admin Only)

#### Validate Configuration

```http
GET /config/validate
Authorization: Bearer <admin-token>
```

**Response (200):**
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

#### Reload Configuration

```http
POST /config/reload
Authorization: Bearer <admin-token>
```

### Graceful Shutdown (Admin Only)

```http
POST /system/shutdown
Authorization: Bearer <admin-token>
```

Initiates a graceful shutdown. Returns immediately; connections are drained over the configured grace period.

---

## WebSocket Usage

DATS provides three real-time WebSocket feeds. All require authentication via a `token` query parameter.

### Connection

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/decisions?token=eyJhbGciOiJIUzI1NiIs...');

ws.onopen = () => {
  console.log('Connected to decision stream');
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log('Received:', msg);
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = (event) => {
  console.log('Connection closed:', event.code, event.reason);
};
```

### Client Actions

After connection, clients can send JSON messages:

```json
{"action": "ping", "timestamp": 1691520000}
```

Server responds:
```json
{"type": "pong", "timestamp": 1691520000}
```

Subscribe to a channel:
```json
{"action": "subscribe", "channel": "decisions"}
```

### Decision Feed — `/ws/decisions`

Receives real-time decision updates as the DecisionEngine generates them.

**Initial message:**
```json
{
  "type": "connected",
  "user": "analyst1",
  "role": "ANALYST",
  "message": "Decision stream active"
}
```

### Market Feed — `/ws/market`

Receives real-time market data ticks.

**Initial message:**
```json
{
  "type": "connected",
  "channel": "market",
  "message": "Market data stream active"
}
```

### System Feed — `/ws/system`

Receives periodic system health and metrics updates every 5 seconds.

**Initial message:**
```json
{
  "type": "connected",
  "channel": "system",
  "message": "System stream active"
}
```

**Periodic update:**
```json
{
  "type": "metrics",
  "counters": {"requests": 15000},
  "gauges": {"active_connections": 12},
  "timestamp": 1691520005.123
}
```

### Error Codes

| Code | Reason | Action |
|------|--------|--------|
| `1008` | Authentication required | Reconnect with valid token |
| `1011` | Server error | Check server logs; retry with backoff |

---

## Error Responses

All errors follow a consistent JSON structure:

```json
{
  "detail": "Error description"
}
```

### HTTP Status Codes

| Status | Meaning | Example |
|--------|---------|---------|
| `200` | Success | Request completed |
| `400` | Bad Request | Invalid request body |
| `401` | Unauthorized | Missing or invalid token |
| `403` | Forbidden | Insufficient role permissions |
| `404` | Not Found | Resource does not exist |
| `422` | Validation Error | Pydantic validation failure |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Internal Server Error | Unexpected server error |

### Validation Error Format

```json
{
  "detail": [
    {
      "loc": ["body", "quantity"],
      "msg": "ensure this value is greater than 0",
      "type": "value_error.number.not_gt"
    }
  ]
}
```

---

## Rate Limits

| Endpoint | Limit | Window | Scope |
|----------|-------|--------|-------|
| `POST /auth/login` | 5 requests | 60 seconds | Per IP address |

All other endpoints are not rate-limited by default. Rate limiting can be enabled globally via middleware configuration if required.

---

*DATS Beta v1.0 — Engineering Documentation*
