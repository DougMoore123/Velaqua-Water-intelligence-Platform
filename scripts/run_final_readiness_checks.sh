#!/usr/bin/env bash
set -euo pipefail

COMPARE_REPORT="${COMPARE_REPORT:-blue_green_compare.json}"
RUN_AZURE_TESTS="${RUN_AZURE_TESTS:-false}"

ruff check services ml scripts tests platform
pytest -q

python scripts/check_model_deployment_gate.py
python scripts/check_human_approval_gate.py

if [[ "$RUN_AZURE_TESTS" == "true" ]]; then
  ./scripts/blue_green_compare_v1.sh | tee "$COMPARE_REPORT"
  COMPARE_REPORT="$COMPARE_REPORT" ./scripts/promote_green_v1.sh
  ./scripts/rollback_to_blue_v1.sh
  ./scripts/smoke_test_realtime_endpoint_v1.sh
fi

echo "Final readiness checks completed."
