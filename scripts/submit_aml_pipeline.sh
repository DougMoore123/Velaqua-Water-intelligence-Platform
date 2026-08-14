#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${AZURE_ML_SUBSCRIPTION_ID:-}" || -z "${AZURE_ML_RESOURCE_GROUP:-}" || -z "${AZURE_ML_WORKSPACE:-}" ]]; then
  echo "Set AZURE_ML_SUBSCRIPTION_ID, AZURE_ML_RESOURCE_GROUP, and AZURE_ML_WORKSPACE"
  exit 1
fi

az account set --subscription "$AZURE_ML_SUBSCRIPTION_ID"

az ml component create \
  --resource-group "$AZURE_ML_RESOURCE_GROUP" \
  --workspace-name "$AZURE_ML_WORKSPACE" \
  --file ml/training/config/train-component.yml

az ml job create \
  --resource-group "$AZURE_ML_RESOURCE_GROUP" \
  --workspace-name "$AZURE_ML_WORKSPACE" \
  --file ml/training/config/pipeline-job.yml

echo "AML pipeline submitted successfully."
