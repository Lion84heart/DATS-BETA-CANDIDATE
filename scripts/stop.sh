#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# DATS — System Shutdown Script
# =============================================================================
# Usage: ./scripts/stop.sh [local|docker]
# Stops the DATS platform gracefully
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MODE="${1:-local}"

echo "=== DATS — System Shutdown ==="
echo "Mode: $MODE"
echo ""

if [ "$MODE" = "docker" ]; then
    echo "[1/2] Stopping Docker containers..."
    cd "$PROJECT_DIR"
    docker-compose down
    echo "OK: Containers stopped"

    echo ""
    echo "[2/2] Verifying cleanup..."
    if docker ps | grep -q "dats-"; then
        echo "WARNING: Some DATS containers still running"
    else
        echo "OK: All DATS containers removed"
    fi

    echo ""
    echo "=== Shutdown Complete (Docker) ==="
    echo ""

elif [ "$MODE" = "local" ]; then
    echo "[1/3] Checking for running process..."
    PID_FILE="$PROJECT_DIR/.dats.pid"

    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Found process: PID $PID"

            echo ""
            echo "[2/3] Sending graceful shutdown signal..."
            kill "$PID" 2>/dev/null || true
            sleep 2

            if ps -p "$PID" > /dev/null 2>&1; then
                echo "Process still running, forcing termination..."
                kill -9 "$PID" 2>/dev/null || true
            fi
        fi
        rm -f "$PID_FILE"
    else
        echo "No PID file found. Checking for uvicorn processes..."
        pkill -f "uvicorn src.main:app" 2>/dev/null || true
    fi

    echo ""
    echo "[3/3] Verifying port release..."
    if lsof -i :8000 > /dev/null 2>&1; then
        echo "WARNING: Port 8000 still in use"
    else
        echo "OK: Port 8000 released"
    fi

    echo ""
    echo "=== Shutdown Complete (Local) ==="
    echo ""

else
    echo "ERROR: Unknown mode '$MODE'. Use 'local' or 'docker'."
    exit 1
fi
