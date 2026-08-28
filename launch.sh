#!/usr/bin/env bash
# DATS Platform — One Command Launcher
# Usage: ./launch.sh [web|tui|demo]

set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

MODE="${1:-web}"

echo "========================================"
echo "  DATS Institutional AI Trading Platform"
echo "  Beta v1.0.0"
echo "========================================"
echo ""

# Check Python
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found"
    exit 1
fi

export PYTHONPATH="${APP_DIR}/src:${PYTHONPATH:-}"

# Check if API already running
API_PID=""
if [ -f .dats.pid ] && kill -0 "$(cat .dats.pid)" 2>/dev/null; then
    API_PID=$(cat .dats.pid)
    echo "API server already running (PID: $API_PID)"
else
    # Ensure log directory
    mkdir -p data/logs
    
    # Start API
    echo "[1/3] Starting API server..."
    nohup python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --app-dir src > data/logs/api.log 2>&1 &
    API_PID=$!
    echo $API_PID > .dats.pid
    echo "      PID: $API_PID"
    
    # Wait for health
    for i in {1..30}; do
        if curl -sf http://localhost:8000/health/ > /dev/null 2>&1; then
            echo "[2/3] API ready"
            break
        fi
        sleep 1
        if [ $i -eq 30 ]; then
            echo "ERROR: API failed to start"
            cat data/logs/api.log | tail -20
            exit 1
        fi
    done
fi

# Launch selected interface
case "$MODE" in
    web)
        echo "[3/3] Launching Web Terminal..."
        echo ""
        echo "========================================"
        echo "  Web Terminal Ready"
        echo "========================================"
        echo ""
        echo "  Dashboard:  http://localhost:8000"
        echo "  Terminal:   http://localhost:8000/static/terminal.html"
        echo "  Demo:       http://localhost:8000/static/demo.html"
        echo "  API Docs:   http://localhost:8000/docs"
        echo ""
        echo "  Auth:       admin/admin"
        echo "  Demo Mode:  Click 'Launch Demo Mode' on login"
        echo ""
        ;;
    
    demo)
        echo "[3/3] Launching Demo Dashboard..."
        echo ""
        echo "========================================"
        echo "  Demo Dashboard Ready"
        echo "========================================"
        echo ""
        echo "  Open:  http://localhost:8000/static/demo.html"
        echo ""
        ;;
    
    tui)
        echo "[3/3] Launching TUI Terminal..."
        echo ""
        # Check textual
        if ! python3 -c "import textual" 2>/dev/null; then
            echo "Installing textual..."
            pip install textual --quiet
        fi
        echo "========================================"
        echo "  TUI Terminal Starting..."
        echo "========================================"
        echo ""
        DATS_API_URL="http://localhost:8000" DATS_DEMO=true python3 tui/main.py
        ;;
    
    *)
        echo "Usage: ./launch.sh [web|tui|demo]"
        echo ""
        echo "  web   - Start API + show web URLs (default)"
        echo "  tui   - Start API + launch terminal UI"
        echo "  demo  - Start API + open demo dashboard"
        echo ""
        exit 1
        ;;
esac

echo "  Logs:       tail -f data/logs/api.log"
echo "  Stop API:   kill $(cat .dats.pid)"
echo ""
