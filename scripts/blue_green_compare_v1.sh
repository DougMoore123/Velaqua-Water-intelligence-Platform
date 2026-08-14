#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_NAME="${WORKSPACE_NAME:-WSVelaqua}"
RESOURCE_GROUP="${RESOURCE_GROUP:-Velaqua}"
ENDPOINT_NAME="${ENDPOINT_NAME:-water-intel-online}"
PAYLOAD="${PAYLOAD:-ml/deployment/smoke_payload.json}"

if [[ ! -f "$PAYLOAD" ]]; then
  echo "Payload not found: $PAYLOAD"
  exit 1
fi

tmpdir=$(mktemp -d)
blue_out="$tmpdir/blue.json"
green_out="$tmpdir/green.json"

az ml endpoint realtime update-version -w "$WORKSPACE_NAME" -g "$RESOURCE_GROUP" -n "$ENDPOINT_NAME" --vn blue --tp 100
az ml endpoint realtime update-version -w "$WORKSPACE_NAME" -g "$RESOURCE_GROUP" -n "$ENDPOINT_NAME" --vn green --tp 0
az ml endpoint realtime run -w "$WORKSPACE_NAME" -g "$RESOURCE_GROUP" -n "$ENDPOINT_NAME" --input-data @"$PAYLOAD" > "$blue_out"

az ml endpoint realtime update-version -w "$WORKSPACE_NAME" -g "$RESOURCE_GROUP" -n "$ENDPOINT_NAME" --vn blue --tp 0
az ml endpoint realtime update-version -w "$WORKSPACE_NAME" -g "$RESOURCE_GROUP" -n "$ENDPOINT_NAME" --vn green --tp 100
az ml endpoint realtime run -w "$WORKSPACE_NAME" -g "$RESOURCE_GROUP" -n "$ENDPOINT_NAME" --input-data @"$PAYLOAD" > "$green_out"

python - "$blue_out" "$green_out" <<'PY'
import json
import sys
from pathlib import Path

blue = json.loads(Path(sys.argv[1]).read_text())
green = json.loads(Path(sys.argv[2]).read_text())

blue_scores = [p["score"] for p in blue.get("predictions", [])]
green_scores = [p["score"] for p in green.get("predictions", [])]

if len(blue_scores) != len(green_scores):
    raise SystemExit("Prediction length mismatch between blue and green")

diffs = [abs(b - g) for b, g in zip(blue_scores, green_scores)]
summary = {
    "n_rows": len(diffs),
    "max_score_delta": max(diffs) if diffs else 0.0,
    "mean_score_delta": (sum(diffs) / len(diffs)) if diffs else 0.0,
    "blue": blue,
    "green": green,
}
print(json.dumps(summary, indent=2))
PY
