# Water Intelligence Platform (Azure Reference Implementation)

Repository: https://github.com/DougMoore123/Velaqua-Water-intelligence-Platform

This repository implements an end-to-end system aligned to your architecture diagram:

1. Data sources -> raw landing (ADLS Gen2)
2. Ingestion -> ADF batch and Event Hub streaming paths
3. Data engineering -> Databricks/PySpark bronze-silver-gold
4. Feature + model development -> Azure ML + MLflow
5. Governance + deployment -> AML registry + online/batch endpoints
6. Decision intelligence -> FastAPI incident API
7. GenAI/RAG -> Azure AI Search + Azure OpenAI evidence packaging
8. Business execution -> dashboard/workflow integration contracts
9. MLOps/observability/security -> GitHub Actions, Monitor, Sentinel, Purview, Entra, Key Vault

## Repository Layout

- `infra/bicep`: Azure infrastructure templates
- `platform/ingestion`: ADF and ingestion assets
- `platform/streaming`: streaming ingestion consumer
- `platform/databricks`: PySpark bronze-silver-gold jobs
- `ml/training`: feature engineering, training, evaluation
- `ml/deployment`: AML endpoint deployment specs
- `services/decision_api`: decision intelligence API
- `services/rag_service`: RAG service for evidence packaging
- `.github/workflows`: CI/CD pipelines
- `governance`: observability, security, data governance notes
- `tests`: unit tests

## Quickstart

### 0) Connect Existing Azure Workspace In VS Code

This repository is preconfigured for the existing Azure ML workspace:

- Subscription: `c128462d-138a-4acb-90cf-f3bd7b2dafe9`
- Resource Group: `Velaqua`
- Workspace: `WSVelaqua`
- ADLS Gen2 datastore: `velaqua_adls`

Run:

```bash
chmod +x scripts/connect_workspace.sh
./scripts/connect_workspace.sh
```

The workspace binding file is ` .azureml/config.json ` and can be used by SDK/tools that read AML defaults.

### 1) Prerequisites

- Python 3.11+
- Azure CLI
- Access to Azure subscription and resource group
- (Optional) Databricks workspace + Azure ML workspace

### 2) Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r services/decision_api/requirements.txt
pip install -r services/rag_service/requirements.txt
pip install -r ml/training/requirements.txt
pip install pytest
```

### 3) Run APIs locally

```bash
uvicorn services.rag_service.app.main:app --reload --port 8001
uvicorn services.decision_api.app.main:app --reload --port 8000
```

### 4) Run training locally

```bash
python ml/training/src/train.py \
  --gold-path data/gold/gold_telemetry.parquet \
  --model-output ml/training/artifacts/leak_model.joblib
```

### 5) Run tests

```bash
pytest -q
```

## Deployment Notes

- Deploy core Azure resources with `infra/bicep/main.bicep`.
- Use AML YAML in `ml/deployment` for online and batch endpoints.
- Submit cloud training with `ml/training/config/train-component.yml` and `ml/training/config/pipeline-job.yml`.
- Deploy Databricks orchestration using `platform/databricks/workflows/leak_intel_job.json`.
- ADLS-backed Databricks paths for your environment are in `platform/databricks/config/pipeline_config.velaqua.yaml`.
- CI workflow validates code quality and tests.
- Deploy workflow is a template to extend with your tenant/subscription details.

## Real RAG Integration

The RAG service in `services/rag_service/app/main.py` now supports:

- Retrieval from Azure AI Search index (`AZURE_AI_SEARCH_ENDPOINT`, `AZURE_AI_SEARCH_INDEX`)
- Generation via Azure OpenAI (`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`)
- Credential modes:
  - API key (`AZURE_AI_SEARCH_KEY`, `AZURE_OPENAI_API_KEY`)
  - Managed Identity / Entra (`DefaultAzureCredential`)

If retrieval or generation fails, the service automatically returns deterministic fallback evidence.

## Operational Scripts

```bash
./scripts/submit_aml_pipeline.sh
./scripts/deploy_databricks_job.sh
./scripts/upload_bootstrap_to_azure.sh
./scripts/deploy_realtime_endpoint_v1.sh
./scripts/smoke_test_realtime_endpoint_v1.sh
./scripts/deploy_green_candidate_v1.sh
./scripts/blue_green_compare_v1.sh
./scripts/rollback_to_blue_v1.sh
./scripts/promote_green_v1.sh
./scripts/configure_rag_services.sh
python scripts/index_rag_corpus.py
python scripts/evaluate_rag_quality.py
python scripts/load_test_endpoint.py --url http://localhost:8000/predict
bash scripts/test_autoscaling_v1.sh
bash scripts/configure_monitoring_baseline.sh
bash scripts/configure_security_governance_baseline.sh
python scripts/monitor_operational_metrics.py
python scripts/check_model_deployment_gate.py
python scripts/check_human_approval_gate.py
bash scripts/configure_budget_alerts.sh
bash scripts/review_cost_and_utilization.sh
bash scripts/run_final_readiness_checks.sh
```

`submit_aml_pipeline.sh` creates the AML training component and submits the pipeline job.

`deploy_databricks_job.sh` uploads Spark jobs to DBFS and creates/updates the Databricks multi-task workflow.

`upload_bootstrap_to_azure.sh` registers AML datasets from existing ADLS Gen2 paths in your workspace datastore.

`connect_workspace.sh` binds the local VS Code terminal context to your existing AML workspace and validates ADLS datastore access.

`deploy_realtime_endpoint_v1.sh` creates or updates an AML CLI v1 realtime endpoint version (`blue`) with auth and telemetry flags.

`smoke_test_realtime_endpoint_v1.sh` sends a sample scoring payload to the realtime endpoint for post-deploy validation.

`deploy_green_candidate_v1.sh`, `blue_green_compare_v1.sh`, `rollback_to_blue_v1.sh`, and `promote_green_v1.sh` implement blue/green validation, rollback, and gated promotion.

`configure_rag_services.sh`, `index_rag_corpus.py`, and `evaluate_rag_quality.py` implement RAG setup, indexing, and quality/grounding evaluation.

`load_test_endpoint.py` performs concurrent request load tests and reports throughput and latency percentiles.

`test_autoscaling_v1.sh` runs ramp-load phases for autoscaling validation.

`configure_monitoring_baseline.sh` configures Azure Monitor, Application Insights, Log Analytics, and baseline alerts.

`configure_security_governance_baseline.sh` applies baseline governance setup for Defender, Policy, Purview, and networking restrictions.

`monitor_operational_metrics.py` computes health, latency, errors, drift, quality, and business-outcome monitoring metrics from telemetry logs.

`check_model_deployment_gate.py` enforces model-performance gate requirements before deployment.

`check_human_approval_gate.py` enforces human production-approval metadata before promotion.

`configure_budget_alerts.sh` configures monthly budget and alert notifications.

`review_cost_and_utilization.sh` provides baseline cost and utilization review outputs.

`run_final_readiness_checks.sh` runs consolidated CI/CD readiness checks and optional Azure end-to-end validation.

See `docs/aml_v1_realtime_endpoint_ops.md` for full CLI v1 deployment/auth/RBAC/APIM guidance.
See `docs/blue_green_release_runbook.md` for release gating and rollback flow.
See `docs/rag_quality_and_safety.md` for RAG quality and GenAI safety controls.
See `docs/monitoring_validation_playbook.md` for latency/throughput/autoscaling/failure monitoring validation.
See `governance/slo_and_alerts.md` for SLO and alert thresholds.
See `governance/ownership_and_procedures.md` for ownership, limitations, and incident/retraining procedures.
See `docs/cicd_and_governance_checklist.md` for final CI/CD and approval checklist execution.
See `governance/production_readiness_review.md` for security/architecture/governance readiness sign-off.

## Decision API Operational Features

- `GET /health`: liveness status.
- `GET /ready`: readiness including RAG configuration visibility.
- `POST /predict`: decision response with risk tier, confidence, decision context, and human-approval requirement fields.
- `POST /incident`: authorization-gated incident orchestration and integration fanout.
- `POST /incident/approval`: operator approval/rejection gate for material actions.
- `GET /kpi/executive`: aggregate incident KPI summary for executive reporting.

Runtime controls are available via environment variables:

- `RAG_SERVICE_URL`, `RAG_TIMEOUT_SECONDS`, `RAG_MAX_RETRIES`
- `RATE_LIMIT_WINDOW_SECONDS`, `RATE_LIMIT_MAX_REQUESTS`
- `OPS_DASHBOARD_URL`, `CMMS_WORK_ORDER_URL`, `FIELD_WORKFLOW_URL`, `CUSTOMER_SERVICE_WORKFLOW_URL`, `EXECUTIVE_KPI_URL`
- `GENAI_BLOCKLIST_TERMS`, `RAG_MAX_CONTEXT_CHARS`, `RAG_MIN_RETRIEVED_DOCS`

## Boilerplate Guide

See `docs/boilerplate_map.md` for a quick map of files/folders and purpose.
See `docs/vscode_boilerplate_walkthrough.md` for the step-by-step VS Code walkthrough.

## Key Design Principle

Every layer preserves traceability: source telemetry + transformed features + model decisions + RAG evidence package are linked by `incident_id` and `asset_id`.
