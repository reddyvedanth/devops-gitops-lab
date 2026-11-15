#!/usr/bin/env bash
# Install Argo CD and point it at this repo. Run this on the KillerCoda node,
# after you have pushed this project to a public GitHub repository.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_FILE="${ROOT}/deploy/argocd/application.yaml"

if ! kubectl get nodes >/dev/null 2>&1; then
  echo "kubectl cannot reach a cluster. Start the KillerCoda Kubernetes playground first." >&2
  exit 1
fi

if grep -q "REPLACE_ME" "${APP_FILE}"; then
  echo "Edit deploy/argocd/application.yaml and replace REPLACE_ME, then push, then run this again." >&2
  exit 1
fi

echo "Installing Argo CD..."
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

echo "Allowing Kustomize to render the Helm chart..."
# --load-restrictor is required because the chart lives in deploy/charts
# and the overlay lives in deploy/overlays/lab. Both are in this repo.
kubectl -n argocd patch configmap argocd-cm --type merge \
  -p '{"data":{"kustomize.buildOptions":"--enable-helm --load-restrictor LoadRestrictionsNone"}}'

# The notes app does not need the UI extras. Scaling them down leaves room
# for three web pods and Postgres on a small playground node.
kubectl -n argocd scale deploy/argocd-notifications-controller --replicas=0 || true
kubectl -n argocd scale deploy/argocd-applicationset-controller --replicas=0 || true
kubectl -n argocd scale deploy/argocd-dex-server --replicas=0 || true

kubectl -n argocd rollout status deploy/argocd-repo-server --timeout=300s
kubectl -n argocd rollout restart deploy/argocd-repo-server
kubectl -n argocd rollout status deploy/argocd-repo-server --timeout=300s
kubectl -n argocd rollout status statefulset/argocd-application-controller --timeout=300s

kubectl wait --for=condition=Established crd/applications.argoproj.io --timeout=180s
kubectl apply -f "${APP_FILE}"

echo
echo "Argo CD is syncing. Follow it with:"
echo "  kubectl get application notes -n argocd"
echo "  kubectl get deploy,pods,svc -n notes"
echo
echo "When notes-web is Ready, open the app with:"
echo "  curl -s localhost:30080/health"
echo "  curl -s localhost:30080/notes"
echo "  curl -s -X POST localhost:30080/notes -H 'Content-Type: application/json' -d '{\"body\":\"hello from cli\"}'"
