#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_NAME="${WORKSPACE_NAME:-WSVelaqua}"
RESOURCE_GROUP="${RESOURCE_GROUP:-Velaqua}"
ENDPOINT_NAME="${ENDPOINT_NAME:-water-intel-online}"

az ml endpoint realtime update-version -w "$WORKSPACE_NAME" -g "$RESOURCE_GROUP" -n "$ENDPOINT_NAME" --vn blue --tp 100 --is-default true
az ml endpoint realtime update-version -w "$WORKSPACE_NAME" -g "$RESOURCE_GROUP" -n "$ENDPOINT_NAME" --vn green --tp 0 --is-default false

echo "Rollback complete: blue=100%, green=0%."
