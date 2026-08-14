# Model Performance and Findings Summary

> Generated from current model-suite artifacts. The real-only holdout contains one validation row and one test row; results remain directional until the data-sufficiency gate passes.

## Classification Reports

| Model | Test accuracy | Leak precision | Leak recall | Leak F1 | Test support |
|---|---:|---:|---:|---:|---:|
| isolation_forest | 1.000 | 1.000 | 1.000 | 1.000 | 1 |
| random_forest | 0.000 | 0.000 | 0.000 | 0.000 | 1 |
| xgboost | 0.000 | 0.000 | 0.000 | 0.000 | 1 |

## Findings

### Model evidence

- Dataset rows: **37** (3 real training, 1 real validation, 1 real test).
- Selected candidate: **isolation_forest**.
- Production gate: **BLOCKED**.
- Data sufficiency: **BLOCKED**.
- Required real-data gaps: {'real_train_rows_needed': 197, 'real_val_rows_needed': 29, 'real_test_rows_needed': 99, 'real_test_leaks_needed': 9}.
- The one-row holdout makes class metrics statistically inconclusive; do not use these results as production claims.
- Classification, confusion-matrix, calibration, and threshold-sensitivity results are persisted per model.

### Operational evidence

- Average latency: **145.09 ms**; availability: **99.67%**; error rate: **0.67%**.
- Missing value rate: **7.98%**; prediction drift PSI: **0.032**; confidence drift PSI: **0.205**.
- Runtime metrics use synthetic telemetry and must be replaced with production telemetry before go-live.

## Required Actions

1. Ingest 200 real training rows, 30 real validation rows, 100 real test rows, and 10 real test leak events.
2. Rerun training, classification reports, scenario tests, and the production gate.
3. Replace synthetic logs with production prediction logs and rerun monitoring.
4. Complete the human approval record before any production promotion.

## Artifact Locations

- Aggregate model results: `ml/training/artifacts/model_suite/model_suite_summary.json`
- Classification reports: `governance/model_classification_reports/<model>.json`
- Evaluation reports: `ml/training/artifacts/model_suite/<model>/evaluation_report.json`
- Scenario results: `ml/training/artifacts/model_suite/scenario_test_report.json`
- Monitoring results: `governance/monitoring_report.json`
