#!/usr/bin/env bash
# Generates API traffic so the Grafana panels and the HPA have something to show.
#   ./scripts/load-test.sh [base-url] [seconds] [parallel-workers]
#   default: http://datadrift.localtest.me 120 20
set -euo pipefail
BASE_URL="${1:-http://datadrift.localtest.me}"
DURATION="${2:-120}"
WORKERS="${3:-20}"

echo "Sending traffic to $BASE_URL for ${DURATION}s with $WORKERS workers..."
end=$((SECONDS + DURATION))
worker() {
  while (( SECONDS < end )); do
    curl -s -o /dev/null "$BASE_URL/api/datasets"
    curl -s -o /dev/null "$BASE_URL/api/datasets/summary"
    curl -s -o /dev/null "$BASE_URL/api/datasets/999999"   # a 404, shows up in the error panel
  done
}
for _ in $(seq "$WORKERS"); do worker & done
wait
echo "Load test finished."
