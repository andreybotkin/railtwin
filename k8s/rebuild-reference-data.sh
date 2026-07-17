#!/bin/sh
set -eu

namespace="${K8S_NAMESPACE:-railway}"
deployment="${RAILDBSETUP_DEPLOYMENT:-raildbsetup}"

echo "Requesting forced railroad, topology, schedule and movement-plan rebuild"
kubectl -n "$namespace" exec "deployment/$deployment" -- python -c \
  'import urllib.request; request = urllib.request.Request("http://127.0.0.1:8003/api/v1/setup/all?force=true", method="POST"); print(urllib.request.urlopen(request, timeout=30).read().decode())'

# BackgroundTasks starts after the HTTP response. First require the pod to
# become unready, otherwise an old Ready condition could make the deploy pass
# before the rebuild has even started.
pod="$(kubectl -n "$namespace" get pod -l app.kubernetes.io/name=raildbsetup -o jsonpath='{.items[0].metadata.name}')"
kubectl -n "$namespace" wait --for=condition=Ready=false "pod/$pod" --timeout=60s
kubectl -n "$namespace" wait --for=condition=Ready=true "pod/$pod" --timeout=20m

status="$(kubectl -n "$namespace" exec "deployment/$deployment" -- python -c \
  'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8003/api/v1/setup/status", timeout=30).read().decode())')"
echo "$status"
echo "$status" | grep -q '"ready":true'
echo "$status" | grep -q '"failed":false'
