#!/usr/bin/env bash
set -euo pipefail

CANDIDATE_JSON="${CANDIDATE_JSON:-ml/training/artifacts/model_suite/production_candidate.json}"
WORKSPACE_NAME="${WORKSPACE_NAME:-WSVelaqua}"
RESOURCE_GROUP="${RESOURCE_GROUP:-Velaqua}"
ENDPOINT_NAME="${ENDPOINT_NAME:-water-intel-online}"
APPROVAL_FILE="${APPROVAL_FILE:-governance/production_approval_record.json}"

python scripts/check_model_deployment_gate.py --candidate-json "$CANDIDATE_JSON"

WORKSPACE_NAME="$WORKSPACE_NAME" \
RESOURCE_GROUP="$RESOURCE_GROUP" \
CANDIDATE_JSON="$CANDIDATE_JSON" \
./scripts/register_production_candidate.sh

WORKSPACE_NAME="$WORKSPACE_NAME" \
RESOURCE_GROUP="$RESOURCE_GROUP" \
ENDPOINT_NAME="$ENDPOINT_NAME" \
VERSION_NAME="blue" \
IS_DEFAULT="true" \
./scripts/deploy_realtime_endpoint_v1.sh

WORKSPACE_NAME="$WORKSPACE_NAME" \
RESOURCE_GROUP="$RESOURCE_GROUP" \
ENDPOINT_NAME="$ENDPOINT_NAME" \
./scripts/smoke_test_realtime_endpoint_v1.sh

python scripts/check_human_approval_gate.py --approval-file "$APPROVAL_FILE"

echo "E2E pipeline chain completed: candidate gate -> register -> blue deploy -> smoke -> approval gate."
