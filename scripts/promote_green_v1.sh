#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_NAME="${WORKSPACE_NAME:-WSVelaqua}"
RESOURCE_GROUP="${RESOURCE_GROUP:-Velaqua}"
ENDPOINT_NAME="${ENDPOINT_NAME:-water-intel-online}"
COMPARE_REPORT="${COMPARE_REPORT:-}"
MAX_MEAN_SCORE_DELTA="${MAX_MEAN_SCORE_DELTA:-0.08}"
MAX_MAX_SCORE_DELTA="${MAX_MAX_SCORE_DELTA:-0.20}"

if [[ -z "$COMPARE_REPORT" || ! -f "$COMPARE_REPORT" ]]; then
  echo "Set COMPARE_REPORT to blue/green comparison JSON file path."
  exit 1
fi

python - "$COMPARE_REPORT" "$MAX_MEAN_SCORE_DELTA" "$MAX_MAX_SCORE_DELTA" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
max_mean = float(sys.argv[2])
max_max = float(sys.argv[3])

mean_delta = float(report.get("mean_score_delta", 1e9))
max_delta = float(report.get("max_score_delta", 1e9))

if mean_delta > max_mean or max_delta > max_max:
    raise SystemExit(
        f"Acceptance criteria failed: mean={mean_delta:.4f} (<= {max_mean}), max={max_delta:.4f} (<= {max_max})"
    )
PY

az ml endpoint realtime update-version -w "$WORKSPACE_NAME" -g "$RESOURCE_GROUP" -n "$ENDPOINT_NAME" --vn green --tp 100 --is-default true
az ml endpoint realtime update-version -w "$WORKSPACE_NAME" -g "$RESOURCE_GROUP" -n "$ENDPOINT_NAME" --vn blue --tp 0 --is-default false

echo "Green promoted to 100% traffic after acceptance criteria check."
