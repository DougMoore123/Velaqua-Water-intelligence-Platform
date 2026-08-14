# Boilerplate Map

This document explains what each top-level folder does and how it maps to the architecture.

## Top-Level Folders

- `infra/`: Azure infrastructure templates (Bicep) for core services.
- `platform/`: data ingestion and data engineering runtime assets.
- `ml/`: training/evaluation and AML deployment assets.
- `services/`: FastAPI-based decision intelligence and RAG services.
- `scripts/`: operational scripts for bootstrap, AML submission, Databricks deploy, and upload.
- `docs/`: architecture and operational documentation.
- `governance/`: observability, security, and policy guidance.
- `tests/`: unit tests for service and decision logic.
- `data/`: local sample data and landing zones (raw/bronze/silver/gold).

## Important Boilerplate Files

- `infra/bicep/main.bicep`: deploys storage, ADF, Event Hub, AML, Databricks, Key Vault, AI Search, App Insights.
- `platform/ingestion/adf/pipeline_ingest_raw.json`: ADF batch ingestion pipeline definition.
- `platform/streaming/eventhub_consumer.py`: Event Hub streaming consumer to raw storage.
- `platform/databricks/jobs/*.py`: bronze/silver/gold PySpark jobs.
- `platform/databricks/workflows/leak_intel_job.json`: Databricks workflow orchestration.
- `ml/training/src/train.py`: local training entrypoint (used by AML component).
- `ml/training/config/*.yml`: AML component and pipeline job for cloud training.
- `ml/deployment/*.yml`: AML online and batch endpoint deployment specs.
- `services/decision_api/app/main.py`: prediction and incident API.
- `services/rag_service/app/main.py`: evidence package generation with Search + OpenAI + fallback.
- `.github/workflows/ci.yml`: lint + tests CI pipeline.
- `.github/workflows/deploy.yml`: infrastructure, endpoints, AML pipeline, and Databricks deployment automation.

## Upload Script

- `scripts/upload_bootstrap_to_azure.sh`: uploads raw/bootstrap content and registers AML data assets.
