#!/usr/bin/env bash
set -euo pipefail

: "${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID}"
: "${AZURE_RESOURCE_GROUP:?Set AZURE_RESOURCE_GROUP}"

BUDGET_NAME="${BUDGET_NAME:-waterintel-monthly-budget}"
MONTHLY_BUDGET_USD="${MONTHLY_BUDGET_USD:-2000}"
ALERT_EMAIL="${ALERT_EMAIL:-}"

if [[ -z "$ALERT_EMAIL" ]]; then
  echo "Set ALERT_EMAIL to configure budget alerts"
  exit 1
fi

SCOPE="/subscriptions/${AZURE_SUBSCRIPTION_ID}/resourceGroups/${AZURE_RESOURCE_GROUP}"

az consumption budget create \
  --budget-name "$BUDGET_NAME" \
  --amount "$MONTHLY_BUDGET_USD" \
  --category cost \
  --time-grain monthly \
  --scope "$SCOPE" \
  --start-date "$(date -u +%Y-%m-01)" \
  --end-date "2030-12-31" \
  --notifications '{
    "Actual_GreaterThan_80_Percent": {
      "enabled": true,
      "operator": "GreaterThan",
      "threshold": 80,
      "contactEmails": ["'"$ALERT_EMAIL"'"]
    },
    "Actual_GreaterThan_100_Percent": {
      "enabled": true,
      "operator": "GreaterThan",
      "threshold": 100,
      "contactEmails": ["'"$ALERT_EMAIL"'"]
    }
  }'

echo "Budget and alerts configured."
