#!/usr/bin/env bash
# Build the four images. Usage: build-images.sh [TAG] [REGISTRY_PREFIX]   (defaults: dev, none)
#   deploy/k8s/build-images.sh dev                      # for a local cluster
#   deploy/k8s/build-images.sh 1.4.0 registry.example.com/acme/   # then `docker push` each (note the trailing slash)
set -euo pipefail
cd "$(dirname "$0")/../.."
TAG="${1:-dev}"
REG="${2:-}"

docker build -t "${REG}openprism/api:${TAG}"         --target api apps/api
docker build -t "${REG}openprism/worker-tex:${TAG}"  --target tex apps/api   # TeX Live: compile + template transfer
docker build -t "${REG}openprism/worker-ai:${TAG}"   --target ai  apps/api    # matplotlib/pandas: plots, LLM, arXiv import
docker build -t "${REG}openprism/web:${TAG}" -f apps/frontend/Dockerfile .    # build context is the repo root (imports /design)

echo "Built ${REG}openprism/{api,worker-tex,worker-ai,web}:${TAG}"
