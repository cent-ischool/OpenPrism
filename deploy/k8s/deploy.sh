#!/usr/bin/env bash
# Apply an overlay and wait for it to become healthy. Usage: deploy.sh <overlay> [namespace]   (overlay: local | production)
#
# Jobs have immutable pod templates, so the migration (and local storage-init) Job from the previous release is
# deleted first; the new migration then runs to completion before the rollouts are considered done. The API and
# workers also wait for migrations themselves (an init container), so a rollout never serves a schema it can't use.
set -euo pipefail
cd "$(dirname "$0")"
OVERLAY="${1:?usage: deploy.sh <overlay> [namespace]}"
NS="${2:-openprism}"

kubectl get namespace "$NS" >/dev/null 2>&1 && kubectl -n "$NS" delete job migrate garage-init --ignore-not-found
kubectl apply -k "overlays/${OVERLAY}"

kubectl -n "$NS" wait --for=condition=complete job/migrate --timeout=900s
for deployment in $(kubectl -n "$NS" get deployments -o name); do
  kubectl -n "$NS" rollout status "$deployment" --timeout=600s
done
kubectl -n "$NS" get pods
