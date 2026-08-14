#!/usr/bin/env bash
set -euo pipefail

MONITOR_REPORT="${MONITOR_REPORT:-governance/monitoring_report.json}"
LOAD_TEST_OUTPUT="${LOAD_TEST_OUTPUT:-orchestrator_load_test.json}"
TIMEOUT_TEST_OUTPUT="${TIMEOUT_TEST_OUTPUT:-orchestrator_timeout_test.json}"
LOAD_TEST_URL="${LOAD_TEST_URL:-http://localhost:8000/predict}"
LOAD_TEST_REQUESTS="${LOAD_TEST_REQUESTS:-300}"
LOAD_TEST_CONCURRENCY="${LOAD_TEST_CONCURRENCY:-30}"
TIMEOUT_TEST_REQUESTS="${TIMEOUT_TEST_REQUESTS:-150}"
TIMEOUT_TEST_CONCURRENCY="${TIMEOUT_TEST_CONCURRENCY:-20}"
TIMEOUT_TEST_SECONDS="${TIMEOUT_TEST_SECONDS:-0.25}"
BASELINE_JSONL="${BASELINE_JSONL:-data/monitoring/baseline_predictions.jsonl}"
CURRENT_JSONL="${CURRENT_JSONL:-data/monitoring/current_predictions.jsonl}"

# 1) Monitoring baseline.
./scripts/configure_monitoring_baseline.sh

# 2) Security baseline.
./scripts/configure_security_governance_baseline.sh

# 3) Load test.
python scripts/load_test_endpoint.py \
  --url "$LOAD_TEST_URL" \
  --requests "$LOAD_TEST_REQUESTS" \
  --concurrency "$LOAD_TEST_CONCURRENCY" | tee "$LOAD_TEST_OUTPUT"

# 4) Timeout behavior test.
python scripts/load_test_endpoint.py \
  --url "$LOAD_TEST_URL" \
  --requests "$TIMEOUT_TEST_REQUESTS" \
  --concurrency "$TIMEOUT_TEST_CONCURRENCY" \
  --timeout "$TIMEOUT_TEST_SECONDS" | tee "$TIMEOUT_TEST_OUTPUT"

# 5) Autoscaling probe.
./scripts/test_autoscaling_v1.sh

# 6) Metrics report generation.
python scripts/monitor_operational_metrics.py \
  --baseline "$BASELINE_JSONL" \
  --current "$CURRENT_JSONL" \
  --output "$MONITOR_REPORT"

# 7) SLO gate verdict.
python scripts/evaluate_slo_gate.py \
  --monitor-report "$MONITOR_REPORT" \
  --load-report "$LOAD_TEST_OUTPUT" \
  --timeout-report "$TIMEOUT_TEST_OUTPUT"

echo "Monitoring/Security orchestrator completed with SLO gate pass."
