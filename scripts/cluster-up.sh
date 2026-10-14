#!/usr/bin/env bash
# Creates the local kind cluster and installs the platform pieces DataDrift runs on:
# ingress-nginx, metrics-server (for the HPA) and kube-prometheus-stack (Prometheus + Grafana).
set -euo pipefail
cd "$(dirname "$0")/.."

CLUSTER=datadrift

if kind get clusters | grep -qx "$CLUSTER"; then
  echo "kind cluster '$CLUSTER' already exists"
else
  kind create cluster --config k8s/kind-config.yaml
fi
kubectl config use-context "kind-$CLUSTER"

helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx >/dev/null
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/ >/dev/null
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo update >/dev/null

echo "==> ingress-nginx"
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx --version 4.15.1 \
  -n ingress-nginx --create-namespace -f k8s/ingress-nginx-kind-values.yaml --wait --timeout 5m

echo "==> metrics-server"
helm upgrade --install metrics-server metrics-server/metrics-server --version 3.14.0 \
  -n kube-system -f k8s/metrics-server-values.yaml --wait --timeout 5m

echo "==> kube-prometheus-stack"
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack --version 92.4.0 \
  -n monitoring --create-namespace -f monitoring/kube-prometheus-stack-values.yaml --wait --timeout 10m

kubectl apply -f k8s/namespace.yaml
echo
echo "Cluster ready. Next: ./scripts/deploy-local.sh"
