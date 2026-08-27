#!/bin/sh
set -eu

namespace="${K8S_NAMESPACE:-railway}"
deployment="${RAILDBSETUP_DEPLOYMENT:-raildbsetup}"
local_port="${RAILDBSETUP_LOCAL_PORT:-18003}"
port_forward_log="/tmp/raildbsetup-port-forward-$$.log"
port_forward_pid=""

cleanup() {
  if [ -n "$port_forward_pid" ]; then
    kill "$port_forward_pid" 2>/dev/null || true
    wait "$port_forward_pid" 2>/dev/null || true
  fi
  rm -f "$port_forward_log"
}
trap cleanup EXIT INT TERM

echo "Requesting forced railroad, topology, schedule and movement-plan rebuild"

# Keep the HTTP client outside the raildbsetup cgroup. During a rebuild the
# container can approach its memory limit, and the kernel may otherwise kill
# the temporary `kubectl exec` process with exit code 137 while uvicorn lives on.
kubectl -n "$namespace" port-forward "deployment/$deployment" \
  "$local_port:8003" >"$port_forward_log" 2>&1 &
port_forward_pid=$!

attempt=0
until curl --silent --show-error --fail --max-time 2 \
  "http://127.0.0.1:$local_port/health" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if ! kill -0 "$port_forward_pid" 2>/dev/null; then
    cat "$port_forward_log" >&2
    echo "kubectl port-forward exited before raildbsetup became reachable" >&2
    exit 1
  fi
  if [ "$attempt" -ge 30 ]; then
    cat "$port_forward_log" >&2
    echo "Timed out waiting for the raildbsetup port-forward" >&2
    exit 1
  fi
  sleep 1
done

curl --silent --show-error --fail --max-time 30 \
  -X POST "http://127.0.0.1:$local_port/api/v1/setup/all?force=true"
echo
echo "Reference-data rebuild was accepted and will continue asynchronously in k3s"
