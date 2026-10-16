#!/usr/bin/env bash
# Installs Argo CD on the kind cluster and hands the DataDrift deployment over to it (GitOps).
# Run after ./scripts/cluster-up.sh.
set -euo pipefail
cd "$(dirname "$0")/.."

helm repo add argo https://argoproj.github.io/argo-helm >/dev/null
helm repo update argo >/dev/null

echo "==> argo-cd"
helm upgrade --install argocd argo/argo-cd --version 10.9.5 \
  -n argocd --create-namespace -f argocd/argocd-values.yaml --wait --timeout 10m

# A release installed earlier with deploy-local.sh would fight Argo CD over the same objects.
# Uninstalling it keeps the Postgres volume (PVCs from a StatefulSet are not deleted), so data survives.
if helm status datadrift -n datadrift >/dev/null 2>&1; then
  echo "==> Handing the existing Helm release over to Argo CD"
  helm uninstall datadrift -n datadrift --wait
fi

echo "==> DataDrift Application"
kubectl apply -f argocd/datadrift-application.yaml
echo "Waiting for Argo CD to sync..."
for _ in $(seq 60); do
  status=$(kubectl get application datadrift -n argocd -o jsonpath='{.status.sync.status}/{.status.health.status}' 2>/dev/null || true)
  [[ "$status" == "Synced/Healthy" ]] && break
  sleep 5
done
kubectl get application datadrift -n argocd

echo
echo "Argo CD UI: http://argocd.localtest.me   user: admin   password:"
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
