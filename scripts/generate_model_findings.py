from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _status(value: bool) -> str:
    return "PASS" if value else "BLOCKED"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite-dir", default="ml/training/artifacts/model_suite")
    parser.add_argument("--monitor-report", default="governance/monitoring_report.json")
    parser.add_argument("--output", default="governance/model_findings_summary.md")
    parser.add_argument(
        "--published-dir", default="governance/model_classification_reports"
    )
    args = parser.parse_args()

    suite_dir = Path(args.suite_dir)
    summary = _read_json(suite_dir / "model_suite_summary.json")
    monitor = _read_json(Path(args.monitor_report)) if Path(args.monitor_report).exists() else {}

    lines = [
        "# Model Performance and Findings Summary",
        "",
        (
            "> Generated from current model-suite artifacts. The real-only holdout "
            "contains one validation row and one test row; results remain "
            "directional until the data-sufficiency gate passes."
        ),
        "",
        "## Classification Reports",
        "",
        "| Model | Test accuracy | Leak precision | Leak recall | Leak F1 | Test support |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    reports: dict[str, dict[str, Any]] = {}
    published_dir = Path(args.published_dir)
    published_dir.mkdir(parents=True, exist_ok=True)
    for model in ("isolation_forest", "random_forest", "xgboost"):
        report_path = suite_dir / model / "classification_report.json"
        report = _read_json(report_path)
        reports[model] = report
        (published_dir / f"{model}.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        test = report["test"]
        lines.append(
            f"| {model} | {test['accuracy']:.3f} | {test['leak']['precision']:.3f} | "
            f"{test['leak']['recall']:.3f} | {test['leak']['f1-score']:.3f} | "
            f"{int(test['leak']['support'])} |"
        )

    data = summary["data"]
    sufficiency = summary.get("data_sufficiency", {})
    gate = summary.get("production_gate", {})
    monitor_request = monitor.get("request_metrics", {})
    monitor_quality = monitor.get("data_quality", {})
    monitor_drift = monitor.get("drift", {})
    average_latency = monitor_request.get("average_latency_ms", 0)
    availability = monitor_request.get("availability", 0) * 100
    error_rate = monitor_request.get("error_rate", 0) * 100
    missing_rate = monitor_quality.get("missing_rate", 0) * 100
    prediction_drift = monitor_drift.get("prediction_drift_psi", 0)
    confidence_drift = monitor_drift.get("confidence_drift_psi", 0)

    lines.extend(
        [
            "",
            "## Findings",
            "",
            "### Model evidence",
            "",
            (
                f"- Dataset rows: **{data['rows']}** ("
                f"{data['real_train_rows']} real training, "
                f"{data['real_val_rows']} real validation, "
                f"{data['real_test_rows']} real test)."
            ),
            f"- Selected candidate: **{gate.get('selected_model', 'not available')}**.",
            f"- Production gate: **{_status(bool(gate.get('passed', False)))}**.",
            f"- Data sufficiency: **{_status(bool(sufficiency.get('ready', False)))}**.",
            f"- Required real-data gaps: {sufficiency.get('gaps', {})}.",
            (
                "- The one-row holdout makes class metrics statistically "
                "inconclusive; do not use these results as production claims."
            ),
            (
                "- Classification, confusion-matrix, calibration, and "
                "threshold-sensitivity results are persisted per model."
            ),
            "",
            "### Operational evidence",
        ]
    )

    if monitor_request:
        lines.extend(
            [
                "",
                (
                    f"- Average latency: **{average_latency:.2f} ms**; "
                    f"availability: **{availability:.2f}%**; "
                    f"error rate: **{error_rate:.2f}%**."
                ),
                (
                    f"- Missing value rate: **{missing_rate:.2f}%**; "
                    f"prediction drift PSI: **{prediction_drift:.3f}**; "
                    f"confidence drift PSI: **{confidence_drift:.3f}**."
                ),
                (
                    "- Runtime metrics use synthetic telemetry and must be "
                    "replaced with production telemetry before go-live."
                ),
            ]
        )

    lines.extend(
        [
            "",
            "## Required Actions",
            "",
            (
                "1. Ingest 200 real training rows, 30 real validation rows, "
                "100 real test rows, and 10 real test leak events."
            ),
            "2. Rerun training, classification reports, scenario tests, and "
            "the production gate.",
            "3. Replace synthetic logs with production prediction logs and rerun monitoring.",
            "4. Complete the human approval record before any production promotion.",
            "",
            "## Artifact Locations",
            "",
            (
                "- Aggregate model results: "
                "`ml/training/artifacts/model_suite/model_suite_summary.json`"
            ),
            (
                "- Classification reports: "
                "`governance/model_classification_reports/<model>.json`"
            ),
            (
                "- Evaluation reports: "
                "`ml/training/artifacts/model_suite/<model>/evaluation_report.json`"
            ),
            "- Scenario results: `ml/training/artifacts/model_suite/scenario_test_report.json`",
            "- Monitoring results: `governance/monitoring_report.json`",
        ]
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
