from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate-json",
        default="ml/training/artifacts/model_suite/production_candidate.json",
    )
    parser.add_argument("--min-precision", type=float, default=0.6)
    parser.add_argument("--min-recall", type=float, default=0.6)
    parser.add_argument("--min-pr-auc", type=float, default=0.6)
    parser.add_argument("--max-false-alarms", type=float, default=2.0)
    parser.add_argument("--min-net-value", type=float, default=0.0)
    args = parser.parse_args()

    candidate_path = Path(args.candidate_json)
    if not candidate_path.exists():
        raise SystemExit(f"Candidate file not found: {candidate_path}")

    payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate = payload.get("candidate", {})
    gate = candidate.get("production_gate", {})
    metrics = candidate.get("test_metrics", {})

    checks = {
        "register_ready": bool(payload.get("register_ready", False)),
        "production_gate_passed": bool(gate.get("passed", False)),
        "precision_ok": float(metrics.get("precision", 0.0)) >= args.min_precision,
        "recall_ok": float(metrics.get("recall", 0.0)) >= args.min_recall,
        "pr_auc_ok": float(metrics.get("pr_auc", 0.0)) >= args.min_pr_auc,
        "false_alarm_ok": (
            float(metrics.get("false_alarm_frequency_per_day", 1e9)) <= args.max_false_alarms
        ),
        "net_value_ok": float(metrics.get("business_net_value", -1e9)) > args.min_net_value,
    }

    if not all(checks.values()):
        raise SystemExit(f"Model performance gate failed: {checks}")

    print(json.dumps({"status": "passed", "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
