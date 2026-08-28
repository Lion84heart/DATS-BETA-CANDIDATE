#!/usr/bin/env bash
# =============================================================================
# DATS-BETA-CANDIDATE Kubernetes Rollback Script
# =============================================================================
# Usage:
#   bash deployment/scripts/rollback.sh [options]
#
# Options:
#   --revision N    Rollback to a specific revision (default: previous)
#   --dry-run       Show what would be rolled back without applying
#   --history       Show rollout history
#   --status        Show current rollout status
#   --help          Show this help message
#
# Examples:
#   bash deployment/scripts/rollback.sh              # Rollback to previous revision
#   bash deployment/scripts/rollback.sh --revision 3   # Rollback to revision 3
#   bash deployment/scripts/rollback.sh --history      # View revision history
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NAMESPACE="dats-beta-candidate"
DEPLOYMENT_NAME="dats-beta-candidate"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
log_info() {
    echo -e "${BLUE}[INFO]${NC}  $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC}    $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC}  $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_help() {
    sed -n '/^# ===/,/^# ===/p' "$0" | sed 's/^# //'
}

show_history() {
    log_info "Rollout history for deployment/${DEPLOYMENT_NAME}..."
    kubectl rollout history deployment/${DEPLOYMENT_NAME} -n "${NAMESPACE}"
}

show_status() {
    log_info "Current rollout status..."
    kubectl rollout status deployment/${DEPLOYMENT_NAME} -n "${NAMESPACE}" --timeout=5s || true
    echo ""
    log_info "Current pods:"
    kubectl get pods -n "${NAMESPACE}" -l app=${DEPLOYMENT_NAME}
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    local revision=""
    local dry_run=false
    local show_history_flag=false
    local show_status_flag=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --revision)
                revision="$2"
                shift 2
                ;;
            --dry-run)
                dry_run=true
                shift
                ;;
            --history)
                show_history_flag=true
                shift
                ;;
            --status)
                show_status_flag=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH."
        exit 1
    fi

    # Show history if requested
    if [[ "${show_history_flag}" == true ]]; then
        show_history
        exit 0
    fi

    # Show status if requested
    if [[ "${show_status_flag}" == true ]]; then
        show_status
        exit 0
    fi

    # Show history before rollback for context
    echo "========================================"
    echo "  DATS-BETA-CANDIDATE Rollback"
    echo "========================================"
    echo ""
    log_info "Current rollout history:"
    show_history
    echo ""

    # Determine rollback target
    if [[ -n "${revision}" ]]; then
        log_info "Target revision: ${revision}"
    else
        log_info "Target: previous revision (default)"
    fi

    # Confirm before rolling back
    if [[ "${dry_run}" == false ]]; then
        echo ""
        read -r -p "Proceed with rollback? [y/N]: " confirm
        if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
            log_info "Rollback cancelled by user."
            exit 0
        fi
    fi

    # Perform rollback
    echo ""
    if [[ "${dry_run}" == true ]]; then
        log_info "DRY-RUN: Would execute:"
        if [[ -n "${revision}" ]]; then
            echo "  kubectl rollout undo deployment/${DEPLOYMENT_NAME} -n ${NAMESPACE} --to-revision=${revision}"
        else
            echo "  kubectl rollout undo deployment/${DEPLOYMENT_NAME} -n ${NAMESPACE}"
        fi
        exit 0
    fi

    if [[ -n "${revision}" ]]; then
        log_info "Rolling back to revision ${revision}..."
        kubectl rollout undo deployment/${DEPLOYMENT_NAME} -n "${NAMESPACE}" --to-revision="${revision}"
    else
        log_info "Rolling back to previous revision..."
        kubectl rollout undo deployment/${DEPLOYMENT_NAME} -n "${NAMESPACE}"
    fi

    echo ""
    log_info "Waiting for rollback to complete..."
    if kubectl rollout status deployment/${DEPLOYMENT_NAME} -n "${NAMESPACE}" --timeout=120s; then
        log_success "Rollback completed successfully."
    else
        log_warn "Rollback status check timed out. Verify manually."
    fi

    echo ""
    log_info "Post-rollback pod status:"
    kubectl get pods -n "${NAMESPACE}" -l app=${DEPLOYMENT_NAME}

    echo ""
    echo "========================================"
    log_success "Rollback operation finished."
    echo "========================================"
}

main "$@"
