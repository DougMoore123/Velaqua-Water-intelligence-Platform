#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${AZURE_SUBSCRIPTION_ID:-}" || -z "${AZURE_RESOURCE_GROUP:-}" || -z "${AZURE_ML_WORKSPACE:-}" ]]; then
  echo "Set AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP, and AZURE_ML_WORKSPACE"
  exit 1
fi

ADLS_DATASTORE="${AZURE_ADLS_DATASTORE:-velaqua_adls}"
ADLS_RAW_PATH="${AZURE_ADLS_RAW_PATH:-raw}"
ADLS_GOLD_PATH="${AZURE_ADLS_GOLD_PATH:-gold}"

az account set --subscription "$AZURE_SUBSCRIPTION_ID"

echo "Validating ADLS datastore in workspace..."
az ml datastore show \
  --name "$ADLS_DATASTORE" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --workspace-name "$AZURE_ML_WORKSPACE" \
  -o table

RAW_SPEC="$(mktemp)"
cat > "$RAW_SPEC" <<EOF
{
  "schemaVersion": 1,
  "datasetType": "File",
  "parameters": {
    "path": [
      {
        "datastoreName": "${ADLS_DATASTORE}",
        "relativePath": "${ADLS_RAW_PATH}"
      }
    ]
  },
  "registration": {
    "name": "water_intel_raw_adls",
    "description": "Raw telemetry path in ADLS Gen2",
    "createNewVersion": true,
    "tags": {
      "zone": "raw",
      "source": "adls-gen2"
    }
  }
}
EOF

GOLD_SPEC="$(mktemp)"
cat > "$GOLD_SPEC" <<EOF
{
  "schemaVersion": 1,
  "datasetType": "File",
  "parameters": {
    "path": [
      {
        "datastoreName": "${ADLS_DATASTORE}",
        "relativePath": "${ADLS_GOLD_PATH}"
      }
    ]
  },
  "registration": {
    "name": "water_intel_gold_adls",
    "description": "Gold feature path in ADLS Gen2",
    "createNewVersion": true,
    "tags": {
      "zone": "gold",
      "source": "adls-gen2"
    }
  }
}
EOF

echo "Registering AML datasets from ADLS paths..."
az ml dataset register \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --workspace-name "$AZURE_ML_WORKSPACE" \
  --file "$RAW_SPEC"

az ml dataset register \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --workspace-name "$AZURE_ML_WORKSPACE" \
  --file "$GOLD_SPEC"

rm -f "$RAW_SPEC" "$GOLD_SPEC"

echo "ADLS dataset registration complete."
echo "Datastore: ${ADLS_DATASTORE}, rawPath=${ADLS_RAW_PATH}, goldPath=${ADLS_GOLD_PATH}"
