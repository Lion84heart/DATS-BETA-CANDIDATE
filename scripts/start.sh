#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# DATS — System Startup Script
# =============================================================================
# Usage: ./scripts/start.sh [local|docker]
# Starts the DATS platform in local or Docker mode
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MODE="${1:-local}"

echo "=== DATS — System Startup ==="
echo "Mode: $MODE"
echo ""

if [ "$MODE" = "docker" ]; then
    # Docker mode
    echo "[1/3] Starting services with docker-compose..."
    cd "$PROJECT_DIR"
    docker-compose up -d --build
    echo "OK: Containers started"

    echo ""
    echo "[2/3] Waiting for services to be healthy..."
    sleep 5

    echo ""
    echo "[3/3] Verifying health endpoint..."
    for i in {1..12}; do
        if curl -sf http://localhost:8000/health/ > /dev/null 2>&1; then
            echo "OK: Platform is healthy"
            break
        fi
        if [ "$i" -eq 12 ]; then
            echo "ERROR: Platform failed to start within 60 seconds"
            echo "Check logs: docker-compose logs dats"
            exit 1
        fi
        sleep 5
    done

    echo ""
    echo "=== Startup Complete (Docker) ==="
    echo "API:        http://localhost:8000"
    echo "Dashboard:  http://localhost:8000/operator"
    echo "Prometheus: http://localhost:8000/metrics/prometheus"
    echo "Logs:       docker-compose logs -f dats"
    echo ""

elif [ "$MODE" = "local" ]; then
    # Local mode
    echo "[1/3] Checking environment..."
    if [ -d "$PROJECT_DIR/.venv" ]; then
        source "$PROJECT_DIR/.venv/bin/activate"
        echo "OK: Virtual environment activated"
    else
        echo "WARNING: Virtual environment not found. Using system Python."
        echo "Ensure PYTHONPATH includes src: export PYTHONPATH=src:\$PYTHONPATH"
    fi

    if [ ! -f "$PROJECT_DIR/.env" ]; then
        echo "WARNING: .env not found. Copying from .env.example"
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    fi
    echo "OK: Environment ready"

    echo ""
    echo "[2/3] Verifying dependencies..."
    python3 -c "import fastapi" 2>/dev/null || {
        echo "ERROR: Dependencies not installed. Run ./scripts/setup.sh"
        exit 1
    }
    echo "OK: Dependencies verified"

    echo ""
    echo "[3/3] Starting Uvicorn server..."
    cd "$PROJECT_DIR"
    PYTHONPATH="src:${PYTHONPATH:-}" nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 --log-level info > "$PROJECT_DIR/data/logs/api.log" 2>&1 &
    PID=$!
    echo $PID > "$PROJECT_DIR/.dats.pid"
    sleep 3

    echo "Waiting for platform to start..."
    for i in {1..10}; do
        if curl -sf http://localhost:8000/health/ > /dev/null 2>&1; then
            echo "OK: Platform started (PID: $PID)"
            break
        fi
        if [ "$i" -eq 10 ]; then
            echo "ERROR: Platform failed to start within 30 seconds"
            kill $PID 2>/dev/null || true
            rm -f "$PROJECT_DIR/.dats.pid"
            exit 1
        fi
        sleep 2
    done

    echo ""
    echo "=== Startup Complete (Local) ==="
    echo "API:        http://localhost:8000"
    echo "Dashboard:  http://localhost:8000/operator"
    echo "Prometheus: http://localhost:8000/metrics/prometheus"
    echo "PID file:   $PROJECT_DIR/.dats.pid"
    echo "Logs:       tail -f $PROJECT_DIR/data/logs/*.log"
    echo ""

else
    echo "ERROR: Unknown mode '$MODE'. Use 'local' or 'docker'."
    exit 1
fi
