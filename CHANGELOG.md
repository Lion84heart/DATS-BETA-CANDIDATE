# Changelog

All notable changes to the DATS (Distributed Algorithmic Trading System) project.

## [1.0.0-beta] - 2026-08-20

### Added
- Professional trading terminal web interface with Bloomberg-style dense layout
- Terminal User Interface (TUI) using Python textual library
- Responsive CSS Grid with breakpoints for mobile, tablet, and desktop
- SVG-based chart rendering with VWAP, support/resistance, crosshair overlays
- Level 2 order book visualization
- Time & Sales feed
- Keyboard shortcuts for all panels (1-8, B, S, Q, ?)
- Complete Docker Compose orchestration with PostgreSQL and Redis
- Kubernetes deployment manifests (namespace, configmap, secret, deployment, service, ingress, HPA)
- Comprehensive test suite with 183 tests across all modules
- JWT-based authentication with 4 RBAC roles
- Paper trading engine with session management
- AI decision center with confidence scoring
- System health monitoring with real-time metrics
- Structured logging with JSON output
- Prometheus metrics endpoint
- Rate limiting and audit logging
- Deployment and rollback scripts

### Changed
- Consolidated from multi-phase development into single production repository
- Standardized all static asset paths to absolute `/static/` references
- Updated all version strings to `1.0.0-beta`
- Refactored authentication to use python-jose for JWT
- Improved Docker build with multi-stage compilation

### Fixed
- Missing `scipy` dependency causing `ModuleNotFoundError` on startup
- Missing `python-jose` dependency causing authentication fallback
- Missing `textual` dependency preventing TUI launch
- Relative CSS/JS paths in index.html causing 404 errors
- Dead code block in `api/auth.py` after `return` statement
- `HTTPException` and `status` not available in `require_role()` scope
- Silent static file mount failures due to `except: pass`

### Security
- JWT tokens with configurable expiration
- Role-based access control (4 roles)
- Rate limiting per endpoint
- Audit logging for all sensitive operations
- Non-root container execution
- Health check endpoint for load balancer integration

## [0.6.0-alpha] - 2026-08-08

### Added
- Initial FastAPI backend with async endpoints
- PostgreSQL integration with SQLAlchemy
- Redis cache layer
- Kafka messaging backbone
- Base trading engine with order lifecycle
- Risk management (position sizing, VaR, kill switch)
- Market data connectors (CoinGecko, Jupiter, Solana RPC)
- Feature store and data quality engine
- Agent framework with reasoning and memory

### Deprecated
- Alpha-phase folder structure
- Phase-based development workflow
