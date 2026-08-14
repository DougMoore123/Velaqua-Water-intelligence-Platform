from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if item:
            rows.append(json.loads(item))
    return rows


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    idx = int(q * (len(sorted_values) - 1))
    return float(sorted_values[idx])


def _psi(baseline: list[float], current: list[float], bins: int = 10) -> float:
    if not baseline or not current:
        return 0.0

    low = min(min(baseline), min(current))
    high = max(max(baseline), max(current))
    if math.isclose(low, high):
        return 0.0

    width = (high - low) / bins

    def bucketize(values: list[float]) -> list[int]:
        counts = [0] * bins
        for value in values:
            idx = min(int((value - low) / width), bins - 1)
            counts[idx] += 1
        return counts

    baseline_counts = bucketize(baseline)
    current_counts = bucketize(current)

    psi_total = 0.0
    for base_count, curr_count in zip(baseline_counts, current_counts):
        base_ratio = max(base_count / len(baseline), 1e-9)
        curr_ratio = max(curr_count / len(current), 1e-9)
        psi_total += (curr_ratio - base_ratio) * math.log(curr_ratio / base_ratio)
    return psi_total


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _schema_changes(
    baseline: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> dict[str, list[str]]:
    baseline_keys = set().union(*(row.keys() for row in baseline)) if baseline else set()
    current_keys = set().union(*(row.keys() for row in current)) if current else set()
    return {
        "added_columns": sorted(current_keys - baseline_keys),
        "removed_columns": sorted(baseline_keys - current_keys),
    }


def _data_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"missing_rate": 0.0, "duplicate_rate": 0.0}

    total_cells = 0
    missing_cells = 0
    seen = Counter()

    for row in rows:
        fingerprint = json.dumps(row, sort_keys=True)
        seen[fingerprint] += 1
        for value in row.values():
            total_cells += 1
            if value is None:
                missing_cells += 1

    duplicates = sum(count - 1 for count in seen.values() if count > 1)
    return {
        "missing_rate": round(missing_cells / max(total_cells, 1), 6),
        "duplicate_rate": round(duplicates / max(len(rows), 1), 6),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default="data/monitoring/baseline_predictions.jsonl")
    parser.add_argument("--current", default="data/monitoring/current_predictions.jsonl")
    parser.add_argument("--output", default="governance/monitoring_report.json")
    args = parser.parse_args()

    baseline = _load_jsonl(Path(args.baseline))
    current = _load_jsonl(Path(args.current))

    baseline_latency = [_safe_float(row.get("latency_ms")) for row in baseline]
    current_latency = [_safe_float(row.get("latency_ms")) for row in current]
    baseline_latency = [v for v in baseline_latency if v is not None]
    current_latency = [v for v in current_latency if v is not None]

    baseline_conf = [_safe_float(row.get("confidence")) for row in baseline]
    current_conf = [_safe_float(row.get("confidence")) for row in current]
    baseline_conf = [v for v in baseline_conf if v is not None]
    current_conf = [v for v in current_conf if v is not None]

    baseline_score = [_safe_float(row.get("score")) for row in baseline]
    current_score = [_safe_float(row.get("score")) for row in current]
    baseline_score = [v for v in baseline_score if v is not None]
    current_score = [v for v in current_score if v is not None]

    observed_current = [row for row in current if row.get("actual_label") in {0, 1}]
    false_alarm_rate = 0.0
    missed_leak_rate = 0.0
    detection_delay_minutes = 0.0

    if observed_current:
        fp = 0
        fn = 0
        negatives = 0
        positives = 0
        delays: list[float] = []

        for row in observed_current:
            pred = int(row.get("predicted_label", 0))
            actual = int(row.get("actual_label", 0))
            if actual == 0:
                negatives += 1
                if pred == 1:
                    fp += 1
            else:
                positives += 1
                if pred == 0:
                    fn += 1
            delay = _safe_float(row.get("detection_delay_minutes"))
            if delay is not None:
                delays.append(delay)

        false_alarm_rate = fp / max(negatives, 1)
        missed_leak_rate = fn / max(positives, 1)
        detection_delay_minutes = mean(delays) if delays else 0.0

    business_impact = [_safe_float(row.get("estimated_business_impact_usd")) for row in current]
    business_impact = [v for v in business_impact if v is not None]

    report = {
        "request_metrics": {
            "average_latency_ms": round(mean(current_latency), 4) if current_latency else 0.0,
            "p95_latency_ms": round(_quantile(current_latency, 0.95), 4),
            "p99_latency_ms": round(_quantile(current_latency, 0.99), 4),
            "throughput_rps_estimate": round(
                len(current_latency) / max(sum(current_latency) / 1000, 1e-9),
                4,
            )
            if current_latency
            else 0.0,
            "error_rate": round(
                sum(1 for row in current if int(row.get("status_code", 200)) >= 400)
                / max(len(current), 1),
                6,
            ),
            "availability": round(
                sum(1 for row in current if int(row.get("status_code", 500)) < 500)
                / max(len(current), 1),
                6,
            ),
        },
        "resource_metrics": {
            "_cpu_values": [
                value
                for value in (_safe_float(row.get("cpu_percent")) for row in current)
                if value is not None
            ],
            "_memory_values": [
                value
                for value in (_safe_float(row.get("memory_percent")) for row in current)
                if value is not None
            ],
        },
        "data_quality": _data_quality(current),
        "schema_changes": _schema_changes(baseline, current),
        "drift": {
            "prediction_drift_psi": round(_psi(baseline_score, current_score), 6),
            "confidence_drift_psi": round(_psi(baseline_conf, current_conf), 6),
        },
        "outcome_quality": {
            "false_alarm_rate": round(false_alarm_rate, 6),
            "missed_leak_rate": round(missed_leak_rate, 6),
            "avg_detection_delay_minutes": round(detection_delay_minutes, 4),
            "avg_business_impact_usd": round(mean(business_impact), 4) if business_impact else 0.0,
        },
    }

    cpu_values = report["resource_metrics"].pop("_cpu_values")
    memory_values = report["resource_metrics"].pop("_memory_values")
    report["resource_metrics"]["avg_cpu_percent"] = (
        round(mean(cpu_values), 4) if cpu_values else 0.0
    )
    report["resource_metrics"]["avg_memory_percent"] = (
        round(mean(memory_values), 4) if memory_values else 0.0
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
