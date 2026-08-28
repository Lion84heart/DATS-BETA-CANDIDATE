# DATS-BETA-CANDIDATE Delivery Map

## Project Identity

- **Name:** DATS — Distributed Algorithmic Trading System
- **Version:** 1.0.0-beta
- **Status:** Production Release Candidate
- **Date:** 2026-08-20

---

## Root Structure

```
DATS-BETA-CANDIDATE/
├── README.md                  # Main project documentation, quick start
├── CHANGELOG.md               # Version history
├── RELEASE_NOTES.md           # Release details and known limitations
├── DELIVERY_MAP.md            # This file — navigation guide
├── LICENSE                    # MIT License
├── Dockerfile                 # Multi-stage container build
├── docker-compose.yml         # Docker Compose orchestration
├── .env.example               # Environment variable template
├── pyproject.toml             # Python project metadata & dependencies
├── launch.sh                  # One-command launcher (web/tui/demo)
│
├── src/                       # Source code (12 modules)
│   ├── api/                   # FastAPI application, routers, static files
│   ├── agents/                # AI agent framework
│   ├── trading/               # Trading engine, execution, risk
│   ├── market/                # Market data connectors
│   ├── intelligence/          # Decision intelligence
│   ├── observability/         # Metrics, logging, health
│   ├── security/              # Auth, audit, rate limiting
│   ├── simulation/            # Paper trading, backtesting
│   ├── system/                # Bootstrap, lifecycle, config
│   ├── infra/                 # Database, Redis, Kafka clients
│   ├── data/                  # Feature store, data quality
│   └── main.py                # Application entry point
│
├── static/                    # Web frontend assets
│   ├── index.html             # SPA login + dashboard
│   ├── terminal.html          # Professional trading terminal
│   ├── demo.html              # Static demo dashboard
│   ├── demo-trading.html      # Trading workspace
│   ├── demo-ai.html           # AI Decision Center
│   ├── demo-paper.html        # Paper Trading Console
│   ├── demo-health.html       # System Health
│   ├── demo-reports.html      # Reports
│   ├── styles.css             # Global stylesheet
│   └── app.js                 # SPA JavaScript
│
├── tui/                       # Terminal User Interface
│   └── main.py                # Textual-based terminal app
│
├── docs/                      # Documentation
│   ├── INSTALLATION.md        # Installation guide
│   ├── DEPLOYMENT.md          # Deployment guide
│   ├── ARCHITECTURE.md        # System architecture
│   ├── CONFIGURATION.md       # Configuration reference
│   ├── API.md                 # API reference
│   ├── TROUBLESHOOTING.md     # Troubleshooting guide
│   ├── OPERATIONAL-SCENARIO-MATRIX.md
│   ├── OPERATOR-ACCEPTANCE-PACKAGE.md
│   ├── UI-VERIFICATION-REPORT.md
│   ├── BUILD-VERIFICATION-REPORT.md
│   ├── FINAL-ENGINEERING-CERTIFICATION-REPORT.md
│   ├── UAT-003-AUTH-RESOLUTION.md
│   ├── FINAL-ENGINEERING-HANDOVER.md
│   └── runbooks/              # 13 operational runbooks
│
├── deployment/                # Deployment artifacts
│   ├── README.md              # Deployment guide
│   ├── k8s/                   # Kubernetes manifests
│   │   ├── namespace.yaml
│   │   ├── configmap.yaml
│   │   ├── secret.yaml
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── ingress.yaml
│   │   └── hpa.yaml
│   └── scripts/               # Deploy & rollback scripts
│       ├── deploy-k8s.sh
│       └── rollback.sh
│
├── config/                    # Configuration templates
│   ├── app.yaml               # Application configuration
│   └── logging.yaml           # Logging configuration
│
├── scripts/                   # Operational scripts
│   ├── setup.sh               # Environment setup
│   ├── start.sh               # Start services
│   ├── stop.sh                # Stop services
│   ├── health_check.sh        # Health verification
│   └── performance_benchmark.py
│
├── tests/                     # Test suite (183 tests)
│   ├── api/
│   ├── trading/
│   ├── agents/
│   ├── market/
│   ├── intelligence/
│   ├── observability/
│   ├── security/
│   ├── simulation/
│   ├── system/
│   ├── infra/
│   ├── data/
│   ├── tools/
│   └── integration/
│
├── data/                      # Runtime data, logs, exports
└── decisions/                 # Decision records
```

---

## Startup Locations

| Interface | URL / Command | Description |
|-----------|-------------|-------------|
| Web Dashboard | `http://localhost:8000` | SPA login and dashboard |
| Trading Terminal | `http://localhost:8000/static/terminal.html` | Professional Bloomberg-style terminal |
| Demo Mode | `http://localhost:8000/static/demo.html` | Pre-populated demo dashboard |
| API Documentation | `http://localhost:8000/docs` | Swagger/OpenAPI UI |
| TUI Terminal | `./launch.sh tui` | Terminal-based interface |
| Docker | `docker compose up -d` | Full containerized deployment |

## Default Credentials

| Username | Password | Role |
|----------|----------|------|
| `admin` | `admin` | Admin |
| `trader` | `trader` | Trader |
| `analyst` | `analyst` | Analyst |
| `operator` | `operator` | Operator |

## Key File Locations

| Purpose | Path |
|---------|------|
| Main application | `src/api/main.py` |
| Authentication | `src/api/auth.py` |
| Static assets | `src/api/static/` |
| Tests | `tests/` |
| Documentation | `docs/` |
| Configuration | `config/` |
| Deployment | `deployment/` |
| Operational scripts | `scripts/` |
| Logs | `data/logs/` |
| Decision records | `decisions/` |

---

*DATS Engineering — v1.0.0-beta*
