#!/usr/bin/env bash
set -euo pipefail

: "${AZURE_RESOURCE_GROUP:?Set AZURE_RESOURCE_GROUP}"
: "${AZURE_LOCATION:?Set AZURE_LOCATION}"
: "${LOG_ANALYTICS_WORKSPACE_NAME:?Set LOG_ANALYTICS_WORKSPACE_NAME}"
: "${APP_INSIGHTS_NAME:?Set APP_INSIGHTS_NAME}"

SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-}"
if [[ -n "$SUBSCRIPTION_ID" ]]; then
  az account set --subscription "$SUBSCRIPTION_ID"
fi

az monitor log-analytics workspace show \
  -g "$AZURE_RESOURCE_GROUP" \
  -n "$LOG_ANALYTICS_WORKSPACE_NAME" >/dev/null 2>&1 || \
az monitor log-analytics workspace create \
  -g "$AZURE_RESOURCE_GROUP" \
  -n "$LOG_ANALYTICS_WORKSPACE_NAME" \
  -l "$AZURE_LOCATION"

LAW_ID=$(az monitor log-analytics workspace show \
  -g "$AZURE_RESOURCE_GROUP" \
  -n "$LOG_ANALYTICS_WORKSPACE_NAME" \
  --query id -o tsv)

az monitor app-insights component show \
  -g "$AZURE_RESOURCE_GROUP" \
  -a "$APP_INSIGHTS_NAME" >/dev/null 2>&1 || \
az monitor app-insights component create \
  -g "$AZURE_RESOURCE_GROUP" \
  -a "$APP_INSIGHTS_NAME" \
  -l "$AZURE_LOCATION" \
  --application-type web \
  --workspace "$LAW_ID"

APP_INSIGHTS_ID=$(az monitor app-insights component show \
  -g "$AZURE_RESOURCE_GROUP" \
  -a "$APP_INSIGHTS_NAME" \
  --query id -o tsv)

ACTION_GROUP_NAME="${ACTION_GROUP_NAME:-waterintel-ops}"
ACTION_GROUP_SHORT="${ACTION_GROUP_SHORT:-wiops}"
OPS_EMAIL="${OPS_EMAIL:-}"

az monitor action-group show \
  -g "$AZURE_RESOURCE_GROUP" \
  -n "$ACTION_GROUP_NAME" >/dev/null 2>&1 || \
az monitor action-group create \
  -g "$AZURE_RESOURCE_GROUP" \
  -n "$ACTION_GROUP_NAME" \
  --short-name "$ACTION_GROUP_SHORT" \
  ${OPS_EMAIL:+--action email ops "$OPS_EMAIL"}

ACTION_GROUP_ID=$(az monitor action-group show -g "$AZURE_RESOURCE_GROUP" -n "$ACTION_GROUP_NAME" --query id -o tsv)

# Latency p95 alert
az monitor metrics alert create \
  -g "$AZURE_RESOURCE_GROUP" \
  -n "waterintel-latency-p95-alert" \
  --scopes "$APP_INSIGHTS_ID" \
  --condition "avg requests/duration > 1000" \
  --description "P95 latency high" \
  --window-size 5m \
  --evaluation-frequency 1m \
  --action "$ACTION_GROUP_ID" || true

# Error-rate alert (failed requests)
az monitor metrics alert create \
  -g "$AZURE_RESOURCE_GROUP" \
  -n "waterintel-failed-requests-alert" \
  --scopes "$APP_INSIGHTS_ID" \
  --condition "avg requests/failed > 5" \
  --description "Failed requests above threshold" \
  --window-size 5m \
  --evaluation-frequency 1m \
  --action "$ACTION_GROUP_ID" || true

# Availability alert
az monitor metrics alert create \
  -g "$AZURE_RESOURCE_GROUP" \
  -n "waterintel-availability-alert" \
  --scopes "$APP_INSIGHTS_ID" \
  --condition "avg availabilityResults/availabilityPercentage < 99.5" \
  --description "Availability below SLO" \
  --window-size 15m \
  --evaluation-frequency 5m \
  --action "$ACTION_GROUP_ID" || true

echo "Monitoring baseline configured."
