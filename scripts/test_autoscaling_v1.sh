#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_NAME="${WORKSPACE_NAME:-WSVelaqua}"
RESOURCE_GROUP="${RESOURCE_GROUP:-Velaqua}"
ENDPOINT_NAME="${ENDPOINT_NAME:-water-intel-online}"
TARGET_URL="${TARGET_URL:-http://localhost:8000/predict}"
PAYLOAD="${PAYLOAD:-ml/deployment/smoke_payload.json}"

# Concurrency ramp to exercise autoscaling and latency behavior.
for concurrency in 10 25 50 75; do
  echo "Running load phase at concurrency=${concurrency}"
  python scripts/load_test_endpoint.py \
    --url "$TARGET_URL" \
    --payload "$PAYLOAD" \
    --requests 300 \
    --concurrency "$concurrency"

done

echo "Current endpoint summary"
az ml endpoint realtime show \
  -w "$WORKSPACE_NAME" \
  -g "$RESOURCE_GROUP" \
  -n "$ENDPOINT_NAME" \
  -o jsonc || true

echo "Autoscaling probe complete. Correlate load phases with Azure Monitor metrics and replica activity."
