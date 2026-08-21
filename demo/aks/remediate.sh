#!/usr/bin/env bash
set -euo pipefail

NAMESPACE=${NAMESPACE:-eip-demo}
DEPLOYMENT=${DEPLOYMENT:-memory-hog}

kubectl -n "$NAMESPACE" get deployment "$DEPLOYMENT" >/dev/null
kubectl -n "$NAMESPACE" patch deployment "$DEPLOYMENT" --type merge -p '{"spec":{"template":{"spec":{"containers":[{"name":"memory-hog","resources":{"requests":{"memory":"64Mi","cpu":"10m"},"limits":{"memory":"256Mi","cpu":"100m"}}}]}}}}'
kubectl -n "$NAMESPACE" rollout status deployment "$DEPLOYMENT" --timeout=120s
kubectl -n "$NAMESPACE" get pods -l app=memory-hog -o wide
