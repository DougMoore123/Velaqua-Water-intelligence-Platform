#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_NAME="${WORKSPACE_NAME:-WSVelaqua}"
RESOURCE_GROUP="${RESOURCE_GROUP:-Velaqua}"
ENDPOINT_NAME="${ENDPOINT_NAME:-water-intel-online}"
COMPARE_REPORT="${COMPARE_REPORT:-blue_green_compare.json}"
LOAD_TEST_OUTPUT="${LOAD_TEST_OUTPUT:-release_gate_load_test.json}"
MAX_MEAN_SCORE_DELTA="${MAX_MEAN_SCORE_DELTA:-0.08}"
MAX_MAX_SCORE_DELTA="${MAX_MAX_SCORE_DELTA:-0.20}"
LOAD_TEST_URL="${LOAD_TEST_URL:-http://localhost:8000/predict}"
LOAD_TEST_REQUESTS="${LOAD_TEST_REQUESTS:-300}"
LOAD_TEST_CONCURRENCY="${LOAD_TEST_CONCURRENCY:-30}"
LOAD_TEST_MIN_SUCCESS="${LOAD_TEST_MIN_SUCCESS:-0.99}"
LOAD_TEST_MAX_P95_MS="${LOAD_TEST_MAX_P95_MS:-1000}"
LOAD_TEST_MAX_P99_MS="${LOAD_TEST_MAX_P99_MS:-1500}"

# Step 4: Compare blue vs green.
WORKSPACE_NAME="$WORKSPACE_NAME" \
RESOURCE_GROUP="$RESOURCE_GROUP" \
ENDPOINT_NAME="$ENDPOINT_NAME" \
./scripts/blue_green_compare_v1.sh | tee "$COMPARE_REPORT"

# Step 5: Promote green only if acceptance criteria pass.
WORKSPACE_NAME="$WORKSPACE_NAME" \
RESOURCE_GROUP="$RESOURCE_GROUP" \
ENDPOINT_NAME="$ENDPOINT_NAME" \
COMPARE_REPORT="$COMPARE_REPORT" \
MAX_MEAN_SCORE_DELTA="$MAX_MEAN_SCORE_DELTA" \
MAX_MAX_SCORE_DELTA="$MAX_MAX_SCORE_DELTA" \
./scripts/promote_green_v1.sh

# Step 6: Post-promotion smoke test.
WORKSPACE_NAME="$WORKSPACE_NAME" \
RESOURCE_GROUP="$RESOURCE_GROUP" \
ENDPOINT_NAME="$ENDPOINT_NAME" \
./scripts/smoke_test_realtime_endpoint_v1.sh

# Step 7: Post-promotion load test with pass/fail thresholds.
python scripts/load_test_endpoint.py \
  --url "$LOAD_TEST_URL" \
  --requests "$LOAD_TEST_REQUESTS" \
  --concurrency "$LOAD_TEST_CONCURRENCY" | tee "$LOAD_TEST_OUTPUT"

python - "$LOAD_TEST_OUTPUT" "$LOAD_TEST_MIN_SUCCESS" "$LOAD_TEST_MAX_P95_MS" "$LOAD_TEST_MAX_P99_MS" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
min_success = float(sys.argv[2])
max_p95 = float(sys.argv[3])
max_p99 = float(sys.argv[4])

success_rate = float(report.get("success_rate", 0.0))
p95 = float(report.get("latency_ms_p95", 1e9) or 1e9)
p99 = float(report.get("latency_ms_p99", 1e9) or 1e9)

if success_rate < min_success:
    raise SystemExit(f"Release gate failed: success_rate={success_rate:.4f} < {min_success:.4f}")
if p95 > max_p95:
    raise SystemExit(f"Release gate failed: p95={p95:.2f}ms > {max_p95:.2f}ms")
if p99 > max_p99:
    raise SystemExit(f"Release gate failed: p99={p99:.2f}ms > {max_p99:.2f}ms")

print(json.dumps({"status": "load_gate_passed", "success_rate": success_rate, "p95": p95, "p99": p99}, indent=2))
PY

# Step 8: Validate rollback path.
WORKSPACE_NAME="$WORKSPACE_NAME" \
RESOURCE_GROUP="$RESOURCE_GROUP" \
ENDPOINT_NAME="$ENDPOINT_NAME" \
./scripts/rollback_to_blue_v1.sh

WORKSPACE_NAME="$WORKSPACE_NAME" \
RESOURCE_GROUP="$RESOURCE_GROUP" \
ENDPOINT_NAME="$ENDPOINT_NAME" \
./scripts/smoke_test_realtime_endpoint_v1.sh

echo "Release gate steps 4-8 completed successfully."
