#!/usr/bin/env bash
# =============================================================================
# scripts/05-deploy-app.sh
# Build the Docker image and deploy the AI DevOps Agent to Kubernetes
# Run on the Control Plane VM (or any machine with docker + kubectl access)
#
# Usage: bash scripts/05-deploy-app.sh [--api-key <your-openai-key>]
# =============================================================================
set -euo pipefail

IMAGE_NAME="ai-devops-agent"
IMAGE_TAG="1.0.0"
NAMESPACE="ai-devops-agent"
OPENAI_API_KEY="${OPENAI_API_KEY:-}"

# Parse optional --api-key flag
while [[ $# -gt 0 ]]; do
    case "$1" in
        --api-key)
            OPENAI_API_KEY="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1"
            exit 1
            ;;
    esac
done

# ── Validate ──────────────────────────────────────────────────────────────────
if [[ -z "${OPENAI_API_KEY}" ]]; then
    echo "❌  OPENAI_API_KEY is not set."
    echo "    Export it or pass --api-key <key>"
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> [1/7] Building Docker image: ${IMAGE_NAME}:${IMAGE_TAG}"
docker build \
    --file "${REPO_ROOT}/docker/Dockerfile" \
    --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
    "${REPO_ROOT}"

echo "==> [2/7] (Optional) Load image into containerd for single-node clusters"
# If using a local kind / kubeadm cluster without a registry, import directly.
if command -v ctr &>/dev/null; then
    docker save "${IMAGE_NAME}:${IMAGE_TAG}" \
        | ctr --namespace k8s.io images import -
    echo "     Image imported into containerd."
fi

echo "==> [3/7] Creating namespace"
kubectl apply -f "${REPO_ROOT}/k8s/namespace.yaml"

echo "==> [4/7] Creating RBAC resources"
kubectl apply -f "${REPO_ROOT}/k8s/rbac.yaml"

echo "==> [5/7] Creating ConfigMap"
kubectl apply -f "${REPO_ROOT}/k8s/configmap.yaml"

echo "==> [6/7] Creating Secret with OpenAI API key"
# Encode the key and patch the secret template, then apply
ENCODED_KEY=$(echo -n "${OPENAI_API_KEY}" | base64)
sed "s|<base64-encoded-api-key>|${ENCODED_KEY}|g" \
    "${REPO_ROOT}/k8s/secret.yaml" \
    | kubectl apply -f -

echo "==> [7/7] Deploying the application + service"
kubectl apply -f "${REPO_ROOT}/k8s/deployment.yaml"
kubectl apply -f "${REPO_ROOT}/k8s/service.yaml"

echo ""
echo "==> Waiting for pod to become Ready (up to 120 s)..."
kubectl rollout status deployment/ai-devops-agent \
    -n "${NAMESPACE}" --timeout=120s

echo ""
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅  AI DevOps Agent deployed successfully!"
echo ""
echo "   API URL   : http://${NODE_IP}:30800"
echo "   Swagger UI: http://${NODE_IP}:30800/docs"
echo "   Health    : curl http://${NODE_IP}:30800/health"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Useful kubectl commands:"
echo "  kubectl get pods -n ${NAMESPACE}"
echo "  kubectl logs -f deployment/ai-devops-agent -n ${NAMESPACE}"
echo "  kubectl describe pod -l app=ai-devops-agent -n ${NAMESPACE}"
