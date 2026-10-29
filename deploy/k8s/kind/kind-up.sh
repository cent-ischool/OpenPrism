#!/usr/bin/env bash
# Create (or reuse) a local kind cluster with a NetworkPolicy-enforcing CNI (Calico), metrics-server and
# ingress-nginx, and load the images built by build-images.sh. Needs docker, kind and kubectl on PATH.
set -euo pipefail
cd "$(dirname "$0")"
NAME="${KIND_CLUSTER:-openprism}"
TAG="${1:-dev}"
CALICO="${CALICO_VERSION:-v3.29.1}"

if ! kind get clusters 2>/dev/null | grep -qx "$NAME"; then
  kind create cluster --name "$NAME" --config kind-config.yaml --wait 0s
  kubectl apply -f "https://raw.githubusercontent.com/projectcalico/calico/${CALICO}/manifests/calico.yaml"
fi
kubectl -n kube-system rollout status daemonset/calico-node --timeout=300s
kubectl wait --for=condition=Ready nodes --all --timeout=300s

# metrics-server (needed by the HorizontalPodAutoscalers); kind's kubelets use self-signed certificates
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl -n kube-system patch deployment metrics-server --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]' || true

kubectl apply -f https://kind.sigs.k8s.io/examples/ingress/deploy-ingress-nginx.yaml
kubectl -n ingress-nginx rollout status deployment/ingress-nginx-controller --timeout=300s

for image in api worker-tex worker-ai web; do
  kind load docker-image "openprism/${image}:${TAG}" --name "$NAME"
done
echo "Cluster '$NAME' ready. Deploy with: deploy/k8s/deploy.sh local"
