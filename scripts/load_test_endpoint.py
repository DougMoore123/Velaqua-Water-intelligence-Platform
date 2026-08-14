from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx


def run_request(client: httpx.Client, url: str, payload: dict) -> tuple[bool, float]:
    started = time.perf_counter()
    try:
        response = client.post(url, json=payload)
        ok = response.status_code == 200
        status_code = response.status_code
        timeout = False
    except httpx.TimeoutException:
        ok = False
        status_code = 0
        timeout = True
    except httpx.HTTPError:
        ok = False
        status_code = 0
        timeout = False
    latency_ms = (time.perf_counter() - started) * 1000
    return ok, latency_ms, status_code, timeout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000/predict")
    parser.add_argument("--payload", default="ml/deployment/smoke_payload.json")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    with open(args.payload, "r", encoding="utf-8") as f:
        payload = json.load(f)

    latencies: list[float] = []
    successes = 0
    timeout_count = 0
    non_200_count = 0
    network_error_count = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal successes, timeout_count, non_200_count, network_error_count
        with httpx.Client(timeout=args.timeout) as client:
            ok, latency, status_code, timed_out = run_request(client, args.url, payload)
        with lock:
            latencies.append(latency)
            if ok:
                successes += 1
            elif timed_out:
                timeout_count += 1
            elif status_code >= 400:
                non_200_count += 1
            else:
                network_error_count += 1

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for _ in range(args.requests):
            pool.submit(worker)
    elapsed = time.perf_counter() - started

    latencies_sorted = sorted(latencies)
    p95_index = int(0.95 * (len(latencies_sorted) - 1)) if latencies_sorted else 0
    p99_index = int(0.99 * (len(latencies_sorted) - 1)) if latencies_sorted else 0

    summary = {
        "requests": args.requests,
        "successes": successes,
        "success_rate": round(successes / max(args.requests, 1), 4),
        "duration_seconds": round(elapsed, 4),
        "throughput_rps": round(args.requests / max(elapsed, 1e-9), 4),
        "latency_ms_avg": round(statistics.mean(latencies), 4) if latencies else None,
        "latency_ms_p95": round(latencies_sorted[p95_index], 4) if latencies_sorted else None,
        "latency_ms_p99": round(latencies_sorted[p99_index], 4) if latencies_sorted else None,
        "timeouts": timeout_count,
        "http_errors": non_200_count,
        "network_errors": network_error_count,
        "concurrency": args.concurrency,
        "timeout_seconds": args.timeout,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
