#!/usr/bin/env bash
# =============================================================================
# DATS-BETA-CANDIDATE Kubernetes Deployment Script
# =============================================================================
# Usage:
#   bash deployment/scripts/deploy-k8s.sh
#
# This script applies all Kubernetes manifests in the correct dependency order.
# Run this from the DATS-BETA-CANDIDATE project root.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
K8S_DIR="${PROJECT_ROOT}/deployment/k8s"
NAMESPACE="dats-beta-candidate"

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

# Check if kubectl is available and connected
check_kubectl() {
    log_info "Checking kubectl connectivity..."
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH."
        exit 1
    fi
    if ! kubectl cluster-info &> /dev/null; then
        log_error "kubectl cannot connect to a Kubernetes cluster."
        log_error "Ensure your kubeconfig is correct and the cluster is reachable."
        exit 1
    fi
    log_success "kubectl is connected to the cluster."
}

# Verify manifest files exist
check_manifests() {
    log_info "Verifying manifest files..."
    local manifests=(
        "namespace.yaml"
        "configmap.yaml"
        "secret.yaml"
        "deployment.yaml"
        "service.yaml"
        "ingress.yaml"
        "hpa.yaml"
    )
    for manifest in "${manifests[@]}"; do
        local filepath="${K8S_DIR}/${manifest}"
        if [[ ! -f "${filepath}" ]]; then
            log_error "Missing manifest: ${filepath}"
            exit 1
        fi
    done
    log_success "All manifest files found."
}

# Apply a single manifest with error handling
apply_manifest() {
    local filepath="$1"
    local description="$2"
    log_info "Applying ${description}..."
    if kubectl apply -f "${filepath}"; then
        log_success "${description} applied."
    else
        log_error "Failed to apply ${description}."
        exit 1
    fi
}

# Wait for Deployment to be ready
wait_for_deployment() {
    log_info "Waiting for Deployment to be ready (timeout: 120s)..."
    if kubectl wait --for=condition=available --timeout=120s \
        deployment/dats-beta-candidate -n "${NAMESPACE}"; then
        log_success "Deployment is ready."
    else
        log_warn "Deployment did not become ready within 120s."
        log_warn "Check pod status with: kubectl get pods -n ${NAMESPACE}"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    echo "========================================"
    echo "  DATS-BETA-CANDIDATE K8s Deploy"
    echo "========================================"
    echo ""

    check_kubectl
    check_manifests

    echo ""
    log_info "Applying manifests from: ${K8S_DIR}"
    echo ""

    # Apply in dependency order
    apply_manifest "${K8S_DIR}/namespace.yaml"       "Namespace (${NAMESPACE})"
    apply_manifest "${K8S_DIR}/configmap.yaml"       "ConfigMap"
    apply_manifest "${K8S_DIR}/secret.yaml"          "Secret"
    apply_manifest "${K8S_DIR}/deployment.yaml"      "Deployment"
    apply_manifest "${K8S_DIR}/service.yaml"          "Service"
    apply_manifest "${K8S_DIR}/ingress.yaml"          "Ingress"
    apply_manifest "${K8S_DIR}/hpa.yaml"             "HorizontalPodAutoscaler"

    echo ""
    wait_for_deployment

    echo ""
    echo "========================================"
    log_success "Deployment complete!"
    echo "========================================"
    echo ""
    log_info "Useful commands:"
    echo "  kubectl get pods -n ${NAMESPACE}"
    echo "  kubectl get svc -n ${NAMESPACE}"
    echo "  kubectl logs -n ${NAMESPACE} -l app=dats-beta-candidate --tail=100 -f"
    echo "  kubectl port-forward -n ${NAMESPACE} svc/dats-beta-candidate 8000:8000"
    echo ""
}

main "$@"
