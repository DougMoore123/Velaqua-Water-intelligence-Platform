#!/usr/bin/env bash
set -euo pipefail

SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-c128462d-138a-4acb-90cf-f3bd7b2dafe9}"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-Velaqua}"
WORKSPACE_NAME="${AZURE_ML_WORKSPACE:-WSVelaqua}"
ADLS_DATASTORE="${AZURE_ADLS_DATASTORE:-velaqua_adls}"

az account set --subscription "$SUBSCRIPTION_ID"
az configure --defaults group="$RESOURCE_GROUP" workspace="$WORKSPACE_NAME"

az ml workspace show --workspace-name "$WORKSPACE_NAME" --resource-group "$RESOURCE_GROUP" --query "{name:name,location:location,id:id}" -o table
az ml datastore show --name "$ADLS_DATASTORE" --workspace-name "$WORKSPACE_NAME" --resource-group "$RESOURCE_GROUP" --query "{name:name,type:datastoreType,container:containerName,account:accountName}" -o table

echo "Workspace defaults configured for VS Code terminal session."
