#!/usr/bin/env bash
# Registers a handful of realistic dataset snapshots through the public API (POST /api/datasets).
# Usage: ./scripts/seed.sh [base-url]     default: http://localhost:3000
set -euo pipefail
BASE_URL="${1:-http://localhost:3000}"

register() {
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/datasets" \
    -H 'Content-Type: application/json' \
    -d "{\"dataset_name\":\"$1\",\"version_tag\":\"$2\",\"record_count\":$3,\"missing_pct\":$4,\"drift_score\":$5}")
  case "$code" in
    201) echo "  registered  $1@$2  (drift $5)" ;;
    409) echo "  exists      $1@$2" ;;
    *)   echo "  FAILED      $1@$2  (HTTP $code)"; return 1 ;;
  esac
}

# Registers a snapshot with a column profile and no drift score, so the backend computes drift
# against the dataset's last verified baseline.
register_profile() {
  local body code result
  body=$(curl -s -w '\n%{http_code}' -X POST "$BASE_URL/api/datasets" \
    -H 'Content-Type: application/json' \
    -d "{\"dataset_name\":\"$1\",\"version_tag\":\"$2\",\"record_count\":$3,\"missing_pct\":$4,\"profile\":$5}")
  code=$(tail -n1 <<<"$body")
  case "$code" in
    201) result=$(head -n1 <<<"$body" | grep -o '"drift_score":[0-9.]*,"status":"[A-Z_]*","drift_method":"[a-z]*"')
         echo "  registered  $1@$2  ($result)" ;;
    409) echo "  exists      $1@$2" ;;
    *)   echo "  FAILED      $1@$2  (HTTP $code)"; return 1 ;;
  esac
}

echo "Seeding DataDrift at $BASE_URL"
register customer-churn     v1.0-raw       118400   4.2  0.06
register customer-churn     v1.2-cleaned   117950   0.3  0.11
register fraud-transactions v3.1-cleaned   2450000  0.8  0.19
register product-reviews    v2.0-dedup     584210   1.1  0.24
register clinic-readmission v0.9-beta      48230    7.6  0.27
register energy-load        v4.0-hourly    876000   0.0  0.04
# Profiled snapshots: v1 becomes the baseline, v2 matches it, v3 shifts the plan mix and gets flagged.
register_profile loan-applications v1.0 50000 0.4 '{"plan":{"basic":30000,"pro":15000,"team":5000},"region":{"north":20000,"south":30000}}'
register_profile loan-applications v1.1 52000 0.5 '{"plan":{"basic":31000,"pro":15800,"team":5200},"region":{"north":20500,"south":31500}}'
register_profile loan-applications v2.0 51000 0.6 '{"plan":{"basic":5000,"pro":15000,"team":31000},"region":{"north":20000,"south":31000}}'
echo "Done."
