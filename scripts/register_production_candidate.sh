#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_NAME="${WORKSPACE_NAME:-WSVelaqua}"
RESOURCE_GROUP="${RESOURCE_GROUP:-Velaqua}"
CANDIDATE_JSON="${CANDIDATE_JSON:-ml/training/artifacts/model_suite/production_candidate.json}"
ENV_DIR="${ENV_DIR:-ml/training/environment}"
MODEL_NAME="${MODEL_NAME:-water-leak-production-candidate}"
FORCE_REGISTER="${FORCE_REGISTER:-false}"

if [[ ! -f "$CANDIDATE_JSON" ]]; then
  echo "Candidate file not found: $CANDIDATE_JSON"
  exit 1
fi

REGISTER_READY=$(python - "$CANDIDATE_JSON" <<'PY'
import json
import sys
from pathlib import Path
p=Path(sys.argv[1])
obj=json.loads(p.read_text())
print(str(bool(obj.get("register_ready", False))).lower())
PY
)

if [[ "$REGISTER_READY" != "true" && "$FORCE_REGISTER" != "true" ]]; then
  echo "Production gate not passed. Registration blocked."
  echo "If you need an emergency override, set FORCE_REGISTER=true explicitly."
  exit 2
fi

MODEL_PATH=$(python - "$CANDIDATE_JSON" <<'PY'
import json
import sys
from pathlib import Path
p=Path(sys.argv[1])
obj=json.loads(p.read_text())
print(obj["candidate"]["model_artifact"])
PY
)

GIT_SHA=$(python - "$CANDIDATE_JSON" <<'PY'
import json
import sys
from pathlib import Path
p=Path(sys.argv[1])
obj=json.loads(p.read_text())
print(obj["lineage"]["git_commit_sha"])
PY
)

DATA_VERSION=$(python - "$CANDIDATE_JSON" <<'PY'
import json
import sys
from pathlib import Path
p=Path(sys.argv[1])
obj=json.loads(p.read_text())
print(obj["lineage"]["data_version"])
PY
)

FEATURE_VERSION=$(python - "$CANDIDATE_JSON" <<'PY'
import json
import sys
from pathlib import Path
p=Path(sys.argv[1])
obj=json.loads(p.read_text())
print(obj["lineage"]["feature_version"])
PY
)

SELECTED_MODEL=$(python - "$CANDIDATE_JSON" <<'PY'
import json
import sys
from pathlib import Path
p=Path(sys.argv[1])
obj=json.loads(p.read_text())
print(obj["candidate"]["model_name"])
PY
)

az ml environment register \
  -w "$WORKSPACE_NAME" \
  -g "$RESOURCE_GROUP" \
  -d "$ENV_DIR"

az ml model register \
  -w "$WORKSPACE_NAME" \
  -g "$RESOURCE_GROUP" \
  -n "$MODEL_NAME" \
  -p "$MODEL_PATH" \
  --model-framework Custom \
  --description "Water leak detection production candidate from model suite" \
  --tag selected_model="$SELECTED_MODEL" \
  --tag git_sha="$GIT_SHA" \
  --tag data_version="$DATA_VERSION" \
  --tag feature_version="$FEATURE_VERSION" \
  --property register_ready="$REGISTER_READY"

az ml model list -w "$WORKSPACE_NAME" -g "$RESOURCE_GROUP" -o table | head -n 20
