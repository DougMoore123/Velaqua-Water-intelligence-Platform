#!/usr/bin/env bash
set -euo pipefail

ENDPOINT_NAME="${ENDPOINT_NAME:-water-intel-online}"
GREEN_TRAFFIC_PERCENTILE="${GREEN_TRAFFIC_PERCENTILE:-10}"

WORKSPACE_NAME="${WORKSPACE_NAME:-WSVelaqua}" \
RESOURCE_GROUP="${RESOURCE_GROUP:-Velaqua}" \
ENDPOINT_NAME="$ENDPOINT_NAME" \
VERSION_NAME="green" \
TRAFFIC_PERCENTILE="$GREEN_TRAFFIC_PERCENTILE" \
IS_DEFAULT="false" \
"$(dirname "$0")/deploy_realtime_endpoint_v1.sh"

echo "Green candidate deployed with ${GREEN_TRAFFIC_PERCENTILE}% traffic."
