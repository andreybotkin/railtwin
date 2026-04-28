#!/usr/bin/env bash
# deploy.sh — local deployment of Thailand Railway Digital Twin to k3s
#
# Usage:
#   ./deploy.sh                        # normal deploy / update
#   ./deploy.sh --clean-db             # wipe DB before deploying
#   ./deploy.sh --pull-images          # pull images from ghcr.io and import into k3s
#   ./deploy.sh --pull-images --clean-db   # all of the above

set -euo pipefail

REGISTRY="ghcr.io/andreybotkin/railtwin"
SERVICES=(simulation frontend gateway raildatacollector raildbsetup)
K8S_DIR="$(cd "$(dirname "$0")/k8s" && pwd)"
NAMESPACE="railway"

CLEAN_DB=false
PULL_IMAGES=false

for arg in "$@"; do
  case $arg in
    --clean-db)    CLEAN_DB=true ;;
    --pull-images) PULL_IMAGES=true ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

##############################################################
# 1. Namespace
##############################################################
echo "==> Namespace..."
kubectl apply -f "$K8S_DIR/namespace.yaml"
kubectl apply -f "$K8S_DIR/network-policy.yaml"

##############################################################
# 2. imagePullSecret for ghcr.io
##############################################################
if ! kubectl get secret ghcr-registry-secret -n "$NAMESPACE" &>/dev/null; then
  if [[ -z "${GHCR_USER:-}" || -z "${GHCR_TOKEN:-}" ]]; then
    echo ""
    echo "==> imagePullSecret for ghcr.io not found in cluster."
    echo "    Set GHCR_USER and GHCR_TOKEN environment variables,"
    echo "    or create the secret manually:"
    echo "      kubectl create secret docker-registry ghcr-registry-secret \\"
    echo "        --docker-server=ghcr.io \\"
    echo "        --docker-username=<user> \\"
    echo "        --docker-password=<pat-token> \\"
    echo "        -n railway"
    echo ""
    echo "    Continuing deploy — using locally cached images."
  else
    echo "==> Creating imagePullSecret ghcr-registry-secret..."
    kubectl create secret docker-registry ghcr-registry-secret \
      --docker-server=ghcr.io \
      --docker-username="$GHCR_USER" \
      --docker-password="$GHCR_TOKEN" \
      -n "$NAMESPACE" \
      --dry-run=client -o yaml | kubectl apply -f -
  fi
else
  echo "==> imagePullSecret ghcr-registry-secret already exists."
fi

##############################################################
# 3. Pull images from ghcr.io into k3s (optional)
##############################################################
if [[ "$PULL_IMAGES" == "true" ]]; then
  if [[ -z "${GHCR_USER:-}" || -z "${GHCR_TOKEN:-}" ]]; then
    echo "ERROR: GHCR_USER and GHCR_TOKEN must be set for --pull-images."
    exit 1
  fi
  echo "==> Authenticating to ghcr.io..."
  echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin

  for svc in "${SERVICES[@]}"; do
    echo "==> Pulling $REGISTRY/$svc:latest ..."
    docker pull "$REGISTRY/$svc:latest"
    echo "==> Importing $svc into k3s containerd..."
    docker save "$REGISTRY/$svc:latest" | k3s ctr images import -
  done
fi

##############################################################
# 4. Postgres + Redis
##############################################################
echo "==> Postgres..."
kubectl apply -f "$K8S_DIR/postgres/deployment.yaml"
kubectl apply -f "$K8S_DIR/postgres/service.yaml"

echo "==> Redis..."
kubectl apply -f "$K8S_DIR/redis/deployment.yaml"
kubectl apply -f "$K8S_DIR/redis/service.yaml"

##############################################################
# 5. Wipe DB (if requested)
##############################################################
if [[ "$CLEAN_DB" == "true" ]]; then
  echo ""
  echo "==> Wiping database..."

  # Scale dependent services to 0
  for svc in simulation raildatacollector raildbsetup; do
    if kubectl get deployment "$svc" -n "$NAMESPACE" &>/dev/null; then
      echo "    Stopping $svc..."
      kubectl scale deployment "$svc" -n "$NAMESPACE" --replicas=0 || true
    fi
  done

  # Delete postgres deployment and PVC
  echo "    Deleting postgres deployment..."
  kubectl delete deployment postgres -n "$NAMESPACE" --ignore-not-found=true
  echo "    Waiting for pod termination..."
  kubectl wait --for=delete pod -l app.kubernetes.io/name=postgres -n "$NAMESPACE" \
    --timeout=60s 2>/dev/null || true

  echo "    Deleting postgres PVC..."
  kubectl delete pvc postgres-pvc -n "$NAMESPACE" --ignore-not-found=true

  # Recreate postgres
  echo "    Creating clean postgres..."
  kubectl apply -f "$K8S_DIR/postgres/deployment.yaml"
  kubectl apply -f "$K8S_DIR/postgres/service.yaml"
fi

##############################################################
# 6. Wait for Postgres to be ready
##############################################################
echo "==> Waiting for Postgres to be ready..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=postgres \
  -n "$NAMESPACE" --timeout=120s

##############################################################
# 7. Application secrets
##############################################################
echo "==> Applying secrets..."

for manifest in \
  "$K8S_DIR/raildbsetup/secrets.yaml" \
  "$K8S_DIR/simulation/secrets.yaml" \
  "$K8S_DIR/raildatacollector/secrets.yaml"; do
  if [[ -f "$manifest" ]]; then
    kubectl apply -f "$manifest"
  else
    echo "    WARNING: $manifest not found, skipping."
    echo "    Copy secrets.yaml.example → secrets.yaml and fill in the values."
  fi
done

##############################################################
# 8. raildbsetup (schema and seed data)
##############################################################
echo "==> raildbsetup..."
kubectl apply -f "$K8S_DIR/raildbsetup/configmap.yaml"
kubectl apply -f "$K8S_DIR/raildbsetup/deployment.yaml"
kubectl apply -f "$K8S_DIR/raildbsetup/service.yaml"

if [[ "$CLEAN_DB" == "true" ]]; then
  # After DB wipe, scale back up
  kubectl scale deployment raildbsetup -n "$NAMESPACE" --replicas=1
fi

echo "==> Waiting for raildbsetup to be ready (may take a few minutes)..."
kubectl rollout status deployment/raildbsetup -n "$NAMESPACE" --timeout=600s

##############################################################
# 9. Simulation, Gateway, Raildatacollector
##############################################################
echo "==> simulation..."
kubectl apply -f "$K8S_DIR/simulation/configmap.yaml"
kubectl apply -f "$K8S_DIR/simulation/deployment.yaml"
kubectl apply -f "$K8S_DIR/simulation/service.yaml"
kubectl apply -f "$K8S_DIR/simulation/hpa.yaml"

if [[ "$CLEAN_DB" == "true" ]]; then
  kubectl scale deployment simulation -n "$NAMESPACE" --replicas=1
fi

echo "==> gateway..."
kubectl apply -f "$K8S_DIR/gateway/configmap.yaml"
kubectl apply -f "$K8S_DIR/gateway/deployment.yaml"
kubectl apply -f "$K8S_DIR/gateway/service.yaml"

echo "==> raildatacollector..."
kubectl apply -f "$K8S_DIR/raildatacollector/configmap.yaml"
kubectl apply -f "$K8S_DIR/raildatacollector/deployment.yaml"
kubectl apply -f "$K8S_DIR/raildatacollector/service.yaml"

if [[ "$CLEAN_DB" == "true" ]]; then
  kubectl scale deployment raildatacollector -n "$NAMESPACE" --replicas=1
fi

##############################################################
# 10. Frontend + Ingress
##############################################################
echo "==> frontend..."
kubectl apply -f "$K8S_DIR/frontend/deployment.yaml"
kubectl apply -f "$K8S_DIR/frontend/service.yaml"
kubectl apply -f "$K8S_DIR/frontend/ingress.yaml"

##############################################################
# 11. Final status
##############################################################
echo ""
echo "==> Current pod status:"
kubectl get pods -n "$NAMESPACE" -o wide

echo ""
echo "==> Deploy complete."
echo ""
echo "    For local access:"
echo "      kubectl port-forward svc/frontend-service 3000:3000 -n railway &"
echo "      kubectl port-forward svc/gateway-service  8002:8002 -n railway &"
echo ""
echo "    Simulation logs:"
echo "      kubectl logs -f deployment/simulation -n railway"
