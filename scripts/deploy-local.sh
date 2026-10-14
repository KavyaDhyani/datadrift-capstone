#!/usr/bin/env bash
# Deploys DataDrift to the local kind cluster with Helm.
#
#   ./scripts/deploy-local.sh             build images from the working tree, tag them with the
#                                         current Git commit SHA, load them into kind and deploy
#   ./scripts/deploy-local.sh --ghcr SHA  deploy the images CI pushed to GHCR for commit SHA
#                                         (the GHCR packages must be public)
set -euo pipefail
cd "$(dirname "$0")/.."

CLUSTER=datadrift
NAMESPACE=datadrift
RELEASE=datadrift

if [[ "${1:-}" == "--ghcr" ]]; then
  TAG="${2:?usage: deploy-local.sh --ghcr <commit-sha>}"
  OWNER=$(git remote get-url origin | sed -E 's#.*github.com[:/]([^/]+)/.*#\1#' | tr '[:upper:]' '[:lower:]')
  IMAGE_ARGS=(
    --set backend.image.repository="ghcr.io/$OWNER/datadrift-backend"
    --set frontend.image.repository="ghcr.io/$OWNER/datadrift-frontend"
    --set backend.image.pullPolicy=IfNotPresent
    --set frontend.image.pullPolicy=IfNotPresent
  )
  echo "==> Deploying GHCR images ghcr.io/$OWNER/datadrift-*:$TAG"
else
  TAG=$(git rev-parse --short HEAD)
  if [[ -n "$(git status --porcelain -- backend frontend)" ]]; then
    TAG="$TAG-dirty"
  fi
  echo "==> Building images datadrift-*:$TAG"
  docker build -q -t "datadrift-backend:$TAG" ./backend
  docker build -q -t "datadrift-frontend:$TAG" ./frontend
  echo "==> Loading images into kind"
  kind load docker-image "datadrift-backend:$TAG" "datadrift-frontend:$TAG" --name "$CLUSTER"
  IMAGE_ARGS=()
fi

kubectl apply -f k8s/namespace.yaml >/dev/null
echo "==> helm upgrade --install $RELEASE"
helm upgrade --install "$RELEASE" ./helm/datadrift -n "$NAMESPACE" \
  -f helm/datadrift/values-local.yaml \
  --set backend.image.tag="$TAG" --set frontend.image.tag="$TAG" \
  "${IMAGE_ARGS[@]}" --wait --timeout 5m

kubectl get pods -n "$NAMESPACE"
echo
echo "Open http://datadrift.localtest.me"
