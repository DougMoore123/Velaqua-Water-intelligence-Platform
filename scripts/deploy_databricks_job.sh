#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DATABRICKS_HOST:-}" || -z "${DATABRICKS_TOKEN:-}" ]]; then
  echo "Set DATABRICKS_HOST and DATABRICKS_TOKEN"
  exit 1
fi

databricks fs mkdirs dbfs:/water-intel/jobs
databricks fs cp platform/databricks/jobs/data_quality_validate.py dbfs:/water-intel/jobs/data_quality_validate.py --overwrite
databricks fs cp platform/databricks/jobs/bronze_ingest.py dbfs:/water-intel/jobs/bronze_ingest.py --overwrite
databricks fs cp platform/databricks/jobs/silver_transform.py dbfs:/water-intel/jobs/silver_transform.py --overwrite
databricks fs cp platform/databricks/jobs/gold_build.py dbfs:/water-intel/jobs/gold_build.py --overwrite

JOB_NAME="water-intel-bronze-silver-gold"
EXISTING_JOB_ID="$(databricks jobs list --output json | jq -r '.jobs[]? | select(.settings.name == "'"$JOB_NAME"'") | .job_id' | head -n 1)"

if [[ -n "$EXISTING_JOB_ID" && "$EXISTING_JOB_ID" != "null" ]]; then
  jq --argjson job_id "$EXISTING_JOB_ID" '{job_id: $job_id, new_settings: .}' \
    platform/databricks/workflows/leak_intel_job.json > /tmp/dbx_job_reset.json
  databricks jobs reset --json @/tmp/dbx_job_reset.json
  echo "Updated Databricks job: $EXISTING_JOB_ID"
else
  databricks jobs create --json @platform/databricks/workflows/leak_intel_job.json
  echo "Created Databricks job: $JOB_NAME"
fi
