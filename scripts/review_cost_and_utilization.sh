#!/usr/bin/env bash
set -euo pipefail

: "${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID}"
: "${AZURE_RESOURCE_GROUP:?Set AZURE_RESOURCE_GROUP}"

AZURE_ML_WORKSPACE="${AZURE_ML_WORKSPACE:-WSVelaqua}"
ENDPOINT_NAME="${ENDPOINT_NAME:-water-intel-online}"
STORAGE_ACCOUNT_NAME="${STORAGE_ACCOUNT_NAME:-}"
APP_INSIGHTS_NAME="${APP_INSIGHTS_NAME:-}"

az account set --subscription "$AZURE_SUBSCRIPTION_ID"

echo "=== Cost baseline (last 30 days) ==="
az consumption usage list --start-date "$(date -u -d '30 days ago' +%Y-%m-%d)" --end-date "$(date -u +%Y-%m-%d)" -o table | head -n 40 || true

echo "=== Compute utilization proxies (ML endpoint state) ==="
az ml endpoint realtime show -w "$AZURE_ML_WORKSPACE" -g "$AZURE_RESOURCE_GROUP" -n "$ENDPOINT_NAME" -o table || true

echo "=== Storage account summary ==="
if [[ -n "$STORAGE_ACCOUNT_NAME" ]]; then
  az storage account show -g "$AZURE_RESOURCE_GROUP" -n "$STORAGE_ACCOUNT_NAME" -o table || true
fi

echo "=== Monitoring component summary ==="
if [[ -n "$APP_INSIGHTS_NAME" ]]; then
  az monitor app-insights component show -g "$AZURE_RESOURCE_GROUP" -a "$APP_INSIGHTS_NAME" -o table || true
fi
