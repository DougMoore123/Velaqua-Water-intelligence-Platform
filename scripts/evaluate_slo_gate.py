from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--monitor-report", default="governance/monitoring_report.json")
    parser.add_argument("--load-report", default="orchestrator_load_test.json")
    parser.add_argument("--timeout-report", default="orchestrator_timeout_test.json")
    parser.add_argument("--min-availability", type=float, default=0.995)
    parser.add_argument("--max-avg-latency-ms", type=float, default=350.0)
    parser.add_argument("--max-p95-latency-ms", type=float, default=1000.0)
    parser.add_argument("--max-p99-latency-ms", type=float, default=1500.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--min-load-success-rate", type=float, default=0.99)
    parser.add_argument("--max-timeout-rate", type=float, default=0.10)
    args = parser.parse_args()

    monitor = _read_json(args.monitor_report)
    load_report = _read_json(args.load_report)
    timeout_report = _read_json(args.timeout_report)

    request_metrics = monitor.get("request_metrics", {})

    checks = {
        "availability_ok": (
            float(request_metrics.get("availability", 0.0)) >= args.min_availability
        ),
        "avg_latency_ok": (
            float(request_metrics.get("average_latency_ms", 1e9)) <= args.max_avg_latency_ms
        ),
        "p95_latency_ok": (
            float(request_metrics.get("p95_latency_ms", 1e9)) <= args.max_p95_latency_ms
        ),
        "p99_latency_ok": (
            float(request_metrics.get("p99_latency_ms", 1e9)) <= args.max_p99_latency_ms
        ),
        "error_rate_ok": float(request_metrics.get("error_rate", 1.0)) <= args.max_error_rate,
        "load_success_ok": (
            float(load_report.get("success_rate", 0.0)) >= args.min_load_success_rate
        ),
        "timeout_rate_ok": (
            float(timeout_report.get("timeouts", 0))
            / max(float(timeout_report.get("requests", 1)), 1.0)
        ) <= args.max_timeout_rate,
    }

    verdict = {"passed": bool(all(checks.values())), "checks": checks}
    print(json.dumps(verdict, indent=2))

    if not verdict["passed"]:
        raise SystemExit("SLO gate failed")


if __name__ == "__main__":
    main()
