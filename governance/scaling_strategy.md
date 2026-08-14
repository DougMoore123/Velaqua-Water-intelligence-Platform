# Scaling Strategy

## Objective

Maintain latency and availability SLOs while controlling cost for AML realtime endpoint and supporting APIs.

## Endpoint Scaling

- Baseline replica count: 1 for blue and 1 for green during validation.
- Increase replicas when p95 latency exceeds 1000 ms for 10 minutes.
- Increase replicas when CPU exceeds 70 percent for 10 minutes.
- Scale down when p95 latency remains below 400 ms and CPU below 40 percent for 30 minutes.

## API Scaling

- Container scale out based on request rate and latency trends.
- Rate limiting remains enabled to protect downstream dependencies.

## Data and Pipeline Scaling

- Databricks workflow scales worker count during backlog periods.
- Batch jobs use partition-aware processing to minimize skew.

## Cost Guardrails

- Budgets and alerts applied at resource-group scope.
- Weekly utilization review for compute, storage, endpoint, and monitoring costs.
- Disable idle green deployment outside active validation windows.
