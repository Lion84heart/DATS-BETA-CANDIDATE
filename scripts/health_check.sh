#!/bin/bash
# DATS — Automated Health Verification Script
# Version: 1.0
# Date: 2026-08-08

BASE_URL="http://localhost:8000"
FAILED=0

check_endpoint() {
    local path="$1"
    local expected="$2"
    local response
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}${path}")
    response=$(curl -s "${BASE_URL}${path}")
    if [ "$code" -eq 200 ] && echo "$response" | grep -q "$expected"; then
        echo "[PASS] ${path} => ${expected}"
    else
        echo "[FAIL] ${path} => expected ${expected}, got HTTP ${code}: ${response}"
        FAILED=$((FAILED + 1))
    fi
}

echo "=== DATS Health Check ==="
echo "Timestamp: $(date -Iseconds)"
echo ""

check_endpoint "/health/" '"status": 3'
check_endpoint "/status/" '"state"'
check_endpoint "/system/version" '"version": "1.0.0-beta"'
check_endpoint "/diagnostics/runtime" '"python_version"'
check_endpoint "/diagnostics/performance" '"timestamp"'
check_endpoint "/config/validate" '"valid": true'

echo ""
if [ $FAILED -eq 0 ]; then
    echo "=== ALL CHECKS PASSED ==="
    exit 0
else
    echo "=== ${FAILED} CHECK(S) FAILED ==="
    exit 1
fi
