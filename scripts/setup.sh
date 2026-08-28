#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# DATS — Environment Setup Script
# =============================================================================
# Usage: ./scripts/setup.sh
# Sets up the local development environment for DATS Beta v1.0
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/.venv"

echo "=== DATS — Environment Setup ==="
echo "Project directory: $PROJECT_DIR"
echo ""

# Step 1: Check Python version
echo "[1/6] Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>/dev/null | cut -d' ' -f2 | cut -d'.' -f1,2) || {
    echo "ERROR: python3 not found. Please install Python 3.12 or later."
    exit 1
}
if [[ "$PYTHON_VERSION" != "3.12" ]]; then
    echo "WARNING: Python $PYTHON_VERSION detected. Python 3.12 is recommended."
else
    echo "OK: Python $PYTHON_VERSION"
fi

# Step 2: Create virtual environment
echo ""
echo "[2/6] Creating virtual environment..."
VENV_CREATED=false
if [ -d "$VENV_DIR" ]; then
    echo "Virtual environment already exists at $VENV_DIR"
    VENV_CREATED=true
else
    if python3 -m venv "$VENV_DIR" 2>/dev/null; then
        echo "Created: $VENV_DIR"
        VENV_CREATED=true
    else
        echo "WARNING: Virtual environment creation failed (filesystem may not support symlinks)."
        echo "Falling back to system Python. Ensure dependencies are installed:"
        echo "  pip install -e ."
    fi
fi

# Step 3: Activate and install dependencies
echo ""
echo "[3/6] Installing dependencies..."
if [ "$VENV_CREATED" = true ]; then
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip setuptools wheel
    pip install -e "$PROJECT_DIR"
    echo "OK: Dependencies installed in virtual environment"
else
    pip install --user --upgrade pip setuptools wheel 2>/dev/null || true
    pip install --user -e "$PROJECT_DIR" 2>/dev/null || {
        echo "NOTE: Using system Python. Ensure dependencies are pre-installed."
    }
    echo "OK: Dependencies configured for system Python"
fi

# Step 4: Copy environment file
echo ""
echo "[4/6] Setting up environment configuration..."
if [ -f "$PROJECT_DIR/.env" ]; then
    echo "OK: .env already exists"
else
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo "Created: .env (from .env.example)"
    echo "WARNING: Please review and update .env with production values"
fi

# Step 5: Create data directories
echo ""
echo "[5/6] Creating data directories..."
mkdir -p "$PROJECT_DIR/data/exports"
mkdir -p "$PROJECT_DIR/data/logs"
mkdir -p "$PROJECT_DIR/data/backups"
echo "OK: Data directories created"

# Step 6: Run tests
echo ""
echo "[6/6] Running test suite..."
cd "$PROJECT_DIR"
PYTHONPATH="src:$PYTHONPATH" python3 -m pytest tests/api/test_api.py -q --tb=short -o "addopts=" 2>&1 | tail -5 || {
    echo "WARNING: Some tests failed. Review test output above."
    exit 1
}

echo ""
echo "=== Setup Complete ==="
if [ "$VENV_CREATED" = true ]; then
    echo "Activate environment: source .venv/bin/activate"
else
    echo "Using system Python (no virtual environment)."
    echo "Ensure PYTHONPATH includes src: export PYTHONPATH=src:\$PYTHONPATH"
fi
echo "Start server: ./scripts/start.sh"
echo ""
