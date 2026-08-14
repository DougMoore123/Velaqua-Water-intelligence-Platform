#!/usr/bin/env bash
set -euo pipefail

: "${AZURE_RESOURCE_GROUP:?Set AZURE_RESOURCE_GROUP}"
: "${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID}"

az account set --subscription "$AZURE_SUBSCRIPTION_ID"

# Defender for Cloud baseline
az security pricing create -n VirtualMachines --tier Standard || true
az security pricing create -n StorageAccounts --tier Standard || true
az security pricing create -n AppServices --tier Standard || true

# Azure Policy baseline assignment
POLICY_SET_ID="${POLICY_SET_ID:-/providers/Microsoft.Authorization/policySetDefinitions/179d1daa-458f-4e47-8086-2a68d0d6c38f}"
POLICY_ASSIGNMENT_NAME="${POLICY_ASSIGNMENT_NAME:-waterintel-security-baseline}"

az policy assignment show --name "$POLICY_ASSIGNMENT_NAME" >/dev/null 2>&1 || \
az policy assignment create \
  --name "$POLICY_ASSIGNMENT_NAME" \
  --scope "/subscriptions/$AZURE_SUBSCRIPTION_ID/resourceGroups/$AZURE_RESOURCE_GROUP" \
  --policy-set-definition "$POLICY_SET_ID" || true

# Purview account (optional)
if [[ -n "${PURVIEW_ACCOUNT_NAME:-}" && -n "${AZURE_LOCATION:-}" ]]; then
  az purview account show -g "$AZURE_RESOURCE_GROUP" -n "$PURVIEW_ACCOUNT_NAME" >/dev/null 2>&1 || \
  az purview account create -g "$AZURE_RESOURCE_GROUP" -n "$PURVIEW_ACCOUNT_NAME" -l "$AZURE_LOCATION" || true
fi

# Restrict storage networking and public access
if [[ -n "${STORAGE_ACCOUNT_NAME:-}" ]]; then
  az storage account update \
    -g "$AZURE_RESOURCE_GROUP" \
    -n "$STORAGE_ACCOUNT_NAME" \
    --public-network-access Disabled \
    --default-action Deny || true
fi

# Private endpoint bootstrap (requires subnet and target resource ids)
if [[ -n "${PRIVATE_ENDPOINT_SUBNET_ID:-}" && -n "${STORAGE_ACCOUNT_ID:-}" ]]; then
  az network private-endpoint create \
    -g "$AZURE_RESOURCE_GROUP" \
    -n "waterintel-st-private-endpoint" \
    --subnet "$PRIVATE_ENDPOINT_SUBNET_ID" \
    --private-connection-resource-id "$STORAGE_ACCOUNT_ID" \
    --group-id blob \
    --connection-name "waterintel-st-conn" || true
fi

# Sentinel onboarding (if extension available)
if az extension show --name sentinel >/dev/null 2>&1; then
  if [[ -n "${LOG_ANALYTICS_WORKSPACE_NAME:-}" ]]; then
    az sentinel onboarding-state create \
      -g "$AZURE_RESOURCE_GROUP" \
      --workspace-name "$LOG_ANALYTICS_WORKSPACE_NAME" \
      -n default || true
  fi
fi

echo "Security/governance baseline attempted. Validate outputs and permissions."
