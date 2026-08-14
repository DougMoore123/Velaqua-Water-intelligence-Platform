# SLOs, Alerts, and Retraining Triggers

## Service Level Objectives

Availability SLO:
- Target: 99.5 percent monthly availability for prediction and incident endpoints.
- Measure: successful requests where status code is below 500.

Latency SLO:
- Target average latency below 350 ms.
- Target p95 latency below 1000 ms.
- Target p99 latency below 1500 ms.

Error-rate SLO:
- Target 5xx error rate below 1.0 percent over 15-minute windows.

## Alert Thresholds

- Critical: availability below 99.0 percent for 15 minutes.
- Warning: p95 latency above 1000 ms for 10 minutes.
- Critical: p99 latency above 1500 ms for 10 minutes.
- Critical: 5xx error rate above 2.0 percent for 10 minutes.
- Warning: CPU or memory above 80 percent for 15 minutes.

## Data and Model Monitoring Thresholds

- Data quality missing rate above 3 percent.
- Schema change detected (added or removed required columns).
- Data drift PSI above 0.2.
- Prediction drift PSI above 0.2.
- Confidence distribution PSI above 0.2.
- False-alarm rate above 10 percent for validated negatives.
- Missed-leak rate above 5 percent for validated positives.
- Detection delay average above 20 minutes.
- Business impact trend degradation above 15 percent month-over-month.

## Retraining Triggers

- Any drift threshold breach sustained for 3 consecutive daily runs.
- False-alarm or missed-leak breach sustained for 2 weekly windows.
- Detection delay breach in 2 weekly windows.
- Confirmed schema change in upstream production data.
- Major network topology change in EPANET model or asset mapping.

## Incident Response Process (Summary)

1. Alert triage by on-call MLOps engineer.
2. Classify severity and impact region.
3. If model or endpoint risk is high, rollback to blue deployment.
4. Open incident channel and assign incident commander.
5. Publish stakeholder updates every 30 minutes until mitigation.
6. Run post-incident review and retraining decision.
