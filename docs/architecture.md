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

## Note Summary

This architecture defines the operational loop for leak detection and decision support. Telemetry enters the platform, is validated and transformed, scored by the model, routed through the decision layer, and grounded with retrieval evidence before a human-approved action is recommended.

The operating objective is:

$$
\text{Operational Value} = \text{Risk Reduction} + \text{Response Improvement} + \text{Evidence Quality}
$$

The core decision signal is:

$$
\text{Priority Score} = \text{Leak Risk}(x_t) \times \text{Estimated Business Impact}(\$)
$$

Where $x_t$ is the current telemetry snapshot at time $t$. Higher priority scores drive escalation, evidence retrieval, and appropriate field action sequencing.
