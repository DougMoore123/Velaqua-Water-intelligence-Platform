# Monitoring Validation Playbook

## Performance Validation

1. Measure average latency, p95 latency, p99 latency, throughput, and concurrency:

```bash
python scripts/load_test_endpoint.py --url http://localhost:8000/predict --requests 500 --concurrency 50
```

2. Test timeout behavior with strict client timeout:

```bash
python scripts/load_test_endpoint.py --url http://localhost:8000/predict --requests 200 --concurrency 40 --timeout 0.25
```

3. Test failure recovery by running against invalid endpoint then restored endpoint:

```bash
python scripts/load_test_endpoint.py --url http://localhost:9999/predict --requests 50 --concurrency 10
python scripts/load_test_endpoint.py --url http://localhost:8000/predict --requests 200 --concurrency 20
```

4. Test autoscaling behavior by running multiple ramp phases and observing instance count and latency:

```bash
bash scripts/test_autoscaling_v1.sh
```

## Observability Baseline

```bash
bash scripts/configure_monitoring_baseline.sh
```

This configures:
- Azure Monitor metrics alerts
- Application Insights component
- Log Analytics workspace

## Data and Drift Monitoring

Prepare baseline and current prediction logs as JSONL, then run:

```bash
python scripts/monitor_operational_metrics.py \
  --baseline data/monitoring/baseline_predictions.jsonl \
  --current data/monitoring/current_predictions.jsonl \
  --output governance/monitoring_report.json
```

Checks include:
- Endpoint health, latency, errors, CPU, memory
- Data quality and schema changes
- Data, prediction, and confidence drift
- False-alarm, missed-leak, detection delay, business outcome trend

## Security and Governance Baseline

```bash
bash scripts/configure_security_governance_baseline.sh
```

This attempts baseline setup for:
- Defender
- Sentinel onboarding
- Purview account bootstrap
- Azure Policy assignment
- Private endpoint bootstrap
- Storage network restrictions
