#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_NAME="${WORKSPACE_NAME:-WSVelaqua}"
RESOURCE_GROUP="${RESOURCE_GROUP:-Velaqua}"
ENDPOINT_NAME="${ENDPOINT_NAME:-water-intel-online}"
INPUT_DATA="${INPUT_DATA:-ml/deployment/smoke_payload.json}"
SHOW_ENDPOINT_KEYS="${SHOW_ENDPOINT_KEYS:-false}"
SHOW_ACCESS_TOKEN="${SHOW_ACCESS_TOKEN:-false}"

if [[ ! -f "$INPUT_DATA" ]]; then
  echo "Smoke input not found: $INPUT_DATA"
  exit 1
fi

if [[ "$SHOW_ENDPOINT_KEYS" == "true" ]]; then
  az ml endpoint realtime get-keys \
    -w "$WORKSPACE_NAME" \
    -g "$RESOURCE_GROUP" \
    -n "$ENDPOINT_NAME"
fi

if [[ "$SHOW_ACCESS_TOKEN" == "true" ]]; then
  az ml endpoint realtime get-access-token \
    -w "$WORKSPACE_NAME" \
    -g "$RESOURCE_GROUP" \
    -n "$ENDPOINT_NAME"
fi

az ml endpoint realtime run \
  -w "$WORKSPACE_NAME" \
  -g "$RESOURCE_GROUP" \
  -n "$ENDPOINT_NAME" \
  --input-data @"$INPUT_DATA"
