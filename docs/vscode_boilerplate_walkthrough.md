# VS Code Boilerplate Walkthrough

This is the exact scaffold in this workspace, organized so you can inspect and run each layer.

## 1) Start Here (Workspace Wiring)

- Workspace binding: `.azureml/config.json`
- Connect script: `scripts/connect_workspace.sh`
- ADLS dataset registration script: `scripts/upload_bootstrap_to_azure.sh`

Run order for Azure context:

```bash
./scripts/connect_workspace.sh
./scripts/upload_bootstrap_to_azure.sh
```

## 2) Architecture -> Code Map

### Data Sources + Ingestion

- Batch ingestion pipeline (ADF): `platform/ingestion/adf/pipeline_ingest_raw.json`
- Streaming ingestion consumer (Event Hub -> ADLS): `platform/streaming/eventhub_consumer.py`

### Data Engineering (Bronze/Silver/Gold)

- Bronze job: `platform/databricks/jobs/bronze_ingest.py`
- Silver job: `platform/databricks/jobs/silver_transform.py`
- Data quality validator job: `platform/databricks/jobs/data_quality_validate.py`
- Gold job: `platform/databricks/jobs/gold_build.py`
- Databricks workflow: `platform/databricks/workflows/leak_intel_job.json`
- ADLS-specific Databricks config: `platform/databricks/config/pipeline_config.velaqua.yaml`

Checklist coverage implemented:

- Validate complete file inventory
- Validate schemas
- Validate row/column counts
- Validate timestamps
- Validate sampling interval
- Validate pressure/flow/demand alignment
- Validate labels
- Validate leak metadata
- Validate EPANET network topology
- Check missing values
- Check duplicates
- Check invalid/outlier sensor values
- Produce data-quality report
- Create Bronze layer with explicit schema and ingestion metadata
- Write Bronze as Delta/Parquet
- Create Silver layer with standardized timestamps, sensor names, and units

### Model Development + MLOps

- Feature building: `ml/training/src/features.py`
- Evaluation metrics: `ml/training/src/evaluate.py`
- Training entrypoint: `ml/training/src/train.py`
- AML component: `ml/training/config/train-component.yml`
- AML pipeline job: `ml/training/config/pipeline-job.yml`

### Model Deployment

- Online endpoint spec: `ml/deployment/online-endpoint.yml`
- Online deployment spec: `ml/deployment/online-deployment.yml`
- Batch endpoint spec: `ml/deployment/batch-endpoint.yml`
- Batch deployment spec: `ml/deployment/batch-deployment.yml`
- Inference scoring file: `ml/deployment/score.py`

### Decision Intelligence + RAG

- Decision API: `services/decision_api/app/main.py`
- Decision logic: `services/decision_api/app/decision_engine.py`
- Shared API contracts: `services/shared/models.py`
- RAG service: `services/rag_service/app/main.py`

### CI/CD + Governance

- CI workflow: `.github/workflows/ci.yml`
- Deployment workflow: `.github/workflows/deploy.yml`
- Monitoring/governance notes: `governance/monitoring.md`

## 3) Local Run Sequence

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r services/decision_api/requirements.txt
pip install -r services/rag_service/requirements.txt
pip install -r ml/training/requirements.txt
pip install pytest ruff
```

Run APIs:

```bash
uvicorn services.rag_service.app.main:app --reload --port 8001
uvicorn services.decision_api.app.main:app --reload --port 8000
```

Run tests:

```bash
pytest -q
ruff check .
```

## 4) What Is Already Finished

- Workspace is connected to Azure ML `WSVelaqua`.
- ADLS Gen2 datastore `velaqua_adls` is wired into pipeline config.
- AML datasets registered from ADLS paths:
  - `water_intel_raw_adls` version `1`
  - `water_intel_gold_adls` version `1`
- Full scaffold exists for infra, data engineering, ML, API, RAG, CI/CD, and governance.

## 5) Minimal File Tree To Focus On

```text
water-intel-platform/
  .azureml/config.json
  infra/bicep/main.bicep
  platform/ingestion/adf/pipeline_ingest_raw.json
  platform/databricks/jobs/*.py
  platform/databricks/workflows/leak_intel_job.json
  ml/training/src/*.py
  ml/training/config/*.yml
  ml/deployment/*.yml
  services/decision_api/app/*.py
  services/rag_service/app/main.py
  .github/workflows/*.yml
  scripts/*.sh
```

## 6) Note Summary

This walkthrough defines the operational sequence for the platform: connect the cloud workspace, ingest data, validate quality, train and evaluate the model, deploy the decision service, ground evidence with RAG, and enforce release governance. The design preserves end-to-end accountability while allowing each operational layer to be reasoned about independently.

The end-to-end control objective is:

$$
\text{System Health} = \text{Data Quality} \land \text{Model Quality} \land \text{Service Reliability} \land \text{Governance Readiness}
$$

If any single term fails, the platform is not considered release-ready.
