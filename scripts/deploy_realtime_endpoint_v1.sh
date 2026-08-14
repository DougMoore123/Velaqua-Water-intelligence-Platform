#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_NAME="${WORKSPACE_NAME:-WSVelaqua}"
RESOURCE_GROUP="${RESOURCE_GROUP:-Velaqua}"
ENDPOINT_NAME="${ENDPOINT_NAME:-water-intel-online}"
VERSION_NAME="${VERSION_NAME:-blue}"
MODEL_NAME="${MODEL_NAME:-water-leak-production-candidate}"
MODEL_VERSION="${MODEL_VERSION:-}"
MODEL_ID="${MODEL_ID:-}"
ENV_NAME="${ENV_NAME:-water-intel-training-env}"
ENV_VERSION="${ENV_VERSION:-}"
SOURCE_DIRECTORY="${SOURCE_DIRECTORY:-.}"
ENTRY_SCRIPT="${ENTRY_SCRIPT:-ml/deployment/score.py}"
CPU_CORES="${CPU_CORES:-1}"
MEMORY_GB="${MEMORY_GB:-2}"
NUM_REPLICAS="${NUM_REPLICAS:-1}"
SCORING_TIMEOUT_MS="${SCORING_TIMEOUT_MS:-120000}"
TRAFFIC_PERCENTILE="${TRAFFIC_PERCENTILE:-100}"
IS_DEFAULT="${IS_DEFAULT:-true}"
ENABLE_KEY_AUTH="${ENABLE_KEY_AUTH:-true}"
ENABLE_TOKEN_AUTH="${ENABLE_TOKEN_AUTH:-true}"
ENABLE_APP_INSIGHTS="${ENABLE_APP_INSIGHTS:-true}"

if [[ -z "$MODEL_ID" ]]; then
  if [[ -z "$MODEL_VERSION" ]]; then
    MODEL_VERSION=$(az ml model list \
      -w "$WORKSPACE_NAME" \
      -g "$RESOURCE_GROUP" \
      --query "[?name=='$MODEL_NAME'] | sort_by(@, &to_number(version))[-1].version" \
      -o tsv)
  fi

  if [[ -z "$MODEL_VERSION" ]]; then
    echo "Unable to resolve model version for $MODEL_NAME"
    echo "Set MODEL_VERSION or MODEL_ID explicitly."
    exit 1
  fi

  MODEL_ID="azureml:${MODEL_NAME}:${MODEL_VERSION}"
fi

DEPLOY_ARGS=(
  -w "$WORKSPACE_NAME"
  -g "$RESOURCE_GROUP"
  -n "$ENDPOINT_NAME"
  --vn "$VERSION_NAME"
  -m "$MODEL_ID"
  --sd "$SOURCE_DIRECTORY"
  --es "$ENTRY_SCRIPT"
  --cc "$CPU_CORES"
  --gb "$MEMORY_GB"
  --nr "$NUM_REPLICAS"
  --tm "$SCORING_TIMEOUT_MS"
  --tp "$TRAFFIC_PERCENTILE"
  --is-default "$IS_DEFAULT"
)

if [[ -n "$ENV_NAME" ]]; then
  DEPLOY_ARGS+=(--environment-name "$ENV_NAME")
fi
if [[ -n "$ENV_VERSION" ]]; then
  DEPLOY_ARGS+=(--environment-version "$ENV_VERSION")
fi

echo "Deploying endpoint=$ENDPOINT_NAME version=$VERSION_NAME model=$MODEL_ID"

if az ml endpoint realtime show -w "$WORKSPACE_NAME" -g "$RESOURCE_GROUP" -n "$ENDPOINT_NAME" >/dev/null 2>&1; then
  echo "Endpoint exists. Trying create-version first, then update-version if version already exists."
  if ! az ml endpoint realtime create-version "${DEPLOY_ARGS[@]}"; then
    az ml endpoint realtime update-version "${DEPLOY_ARGS[@]}"
  fi
else
  az ml endpoint realtime create-version "${DEPLOY_ARGS[@]}"
fi

az ml endpoint realtime update \
  -w "$WORKSPACE_NAME" \
  -g "$RESOURCE_GROUP" \
  -n "$ENDPOINT_NAME" \
  --ae "$ENABLE_KEY_AUTH" \
  --token-auth-enabled "$ENABLE_TOKEN_AUTH" \
  --ai "$ENABLE_APP_INSIGHTS"

az ml endpoint realtime show \
  -w "$WORKSPACE_NAME" \
  -g "$RESOURCE_GROUP" \
  -n "$ENDPOINT_NAME" \
  -o table
