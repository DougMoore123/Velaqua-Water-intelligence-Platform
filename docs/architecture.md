# Architecture Mapping

This implementation maps directly to your diagram:

- Data Sources: `data/raw` and external connectors represented in `platform/ingestion`.
- Ingestion and Landing: ADF pipeline JSON and Event Hub consumer.
- Data Engineering: Databricks/PySpark jobs for bronze-silver-gold.
- Model Development: local training + AML cloud pipeline in `ml/training/config`.
- Model Governance and Deployment: AML endpoint YAML specs.
- Decision Intelligence: `services/decision_api`.
- GenAI/RAG: `services/rag_service` using Azure AI Search and Azure OpenAI with fallback evidence.
- MLOps and Governance: GitHub Actions and governance controls.

## Contract and Traceability

The system uses `incident_id` as the primary linkage from telemetry-derived model output to decision and evidence packaging.
