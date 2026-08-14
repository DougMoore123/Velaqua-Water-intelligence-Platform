# Monitoring, Security, and Governance

## Observability

- Application telemetry from FastAPI services should be sent to Azure Application Insights.
- Centralized logs and metrics should flow into Azure Monitor + Log Analytics.
- Track model endpoint latency, request volume, and failure rate.
- Measure average, p95, and p99 latency, plus throughput, under concurrent load phases.
- Validate timeout behavior and failure recovery through explicit negative-path load tests.
- Run autoscaling probes with ramped concurrency and correlate to metrics.

## Model Monitoring

- Drift: feature distribution drift against training baselines.
- Quality: precision/recall decay on validated field outcomes.
- Latency: P50/P95 inference latency by endpoint.
- Outcomes: false positives, missed leaks, and business impact.
- Confidence distribution monitoring and drift score tracking.
- Detection delay and business outcome trend monitoring.
- Schema-change and data-quality checks integrated into monitoring jobs.

## Security

- API exposure fronted by Azure API Management.
- Security telemetry and anomaly detection integrated with Microsoft Sentinel.
- Defender for Cloud should be enabled for subscription and relevant services.
- Restrict storage networking, enforce least-privilege access, and enable audit logging.
- Use private networking and private endpoints where required by policy.

## Data Governance

- Register curated datasets in Microsoft Purview.
- Apply Azure Policy for encryption, private endpoints, and approved SKUs.
- Use Entra ID managed identities and Key Vault-backed secret access.

## Operational Baseline Assets

- SLOs, alert thresholds, and retraining triggers: `governance/slo_and_alerts.md`
- Ownership, model limitations, and procedures: `governance/ownership_and_procedures.md`
- Monitoring validation playbook: `docs/monitoring_validation_playbook.md`
- Monitoring metrics job: `scripts/monitor_operational_metrics.py`
- Azure Monitor/App Insights/Log Analytics setup: `scripts/configure_monitoring_baseline.sh`
- Security governance baseline setup: `scripts/configure_security_governance_baseline.sh`
