#!/usr/bin/env bash
set -euo pipefail

: "${AZURE_RESOURCE_GROUP:?Set AZURE_RESOURCE_GROUP}"
: "${AZURE_LOCATION:?Set AZURE_LOCATION}"
: "${AZURE_AI_SEARCH_NAME:?Set AZURE_AI_SEARCH_NAME}"
: "${AZURE_OPENAI_NAME:?Set AZURE_OPENAI_NAME}"

SEARCH_SKU="${SEARCH_SKU:-basic}"
OPENAI_SKU="${OPENAI_SKU:-S0}"
OPENAI_MODEL="${OPENAI_MODEL:-gpt-4o-mini}"
OPENAI_DEPLOYMENT="${OPENAI_DEPLOYMENT:-gpt-4o-mini}"
OPENAI_MODEL_VERSION="${OPENAI_MODEL_VERSION:-latest}"

az search service show -g "$AZURE_RESOURCE_GROUP" -n "$AZURE_AI_SEARCH_NAME" >/dev/null 2>&1 || \
  az search service create -g "$AZURE_RESOURCE_GROUP" -n "$AZURE_AI_SEARCH_NAME" --sku "$SEARCH_SKU" --location "$AZURE_LOCATION"

az cognitiveservices account show -g "$AZURE_RESOURCE_GROUP" -n "$AZURE_OPENAI_NAME" >/dev/null 2>&1 || \
  az cognitiveservices account create \
    -g "$AZURE_RESOURCE_GROUP" \
    -n "$AZURE_OPENAI_NAME" \
    --kind OpenAI \
    --sku "$OPENAI_SKU" \
    --location "$AZURE_LOCATION" \
    --yes

az cognitiveservices account deployment create \
  -g "$AZURE_RESOURCE_GROUP" \
  -n "$AZURE_OPENAI_NAME" \
  --deployment-name "$OPENAI_DEPLOYMENT" \
  --model-name "$OPENAI_MODEL" \
  --model-version "$OPENAI_MODEL_VERSION" \
  --model-format OpenAI || true

echo "Search and OpenAI configuration complete (idempotent)."
