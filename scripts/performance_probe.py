#!/usr/bin/env python3
"""Repeatable HTTP latency probe for the deployed AI-PIM API."""

import argparse
import concurrent.futures
import json
import os
import ssl
import statistics
import sys
import time
import urllib.error
import urllib.request


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * ratio))
    return ordered[index]


def request(url: str, token: str, context: ssl.SSLContext) -> tuple[float, int]:
    started = time.perf_counter()
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=context) as response:
            response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    return (time.perf_counter() - started) * 1000, status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("PIM_ACCESS_TOKEN", "")
    if not token:
        raise SystemExit("PIM_ACCESS_TOKEN is required")

    context = ssl.create_default_context()
    if args.insecure:
        print("warning: TLS certificate verification is disabled", file=sys.stderr)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        results = list(
            executor.map(
                lambda _: request(args.url, token, context),
                range(args.requests),
            )
        )
    elapsed = time.perf_counter() - started
    latencies = [latency for latency, _ in results]
    errors = sum(1 for _, status in results if status >= 400)
    print(
        json.dumps(
            {
                "url": args.url,
                "requests": args.requests,
                "concurrency": args.concurrency,
                "p50_ms": round(statistics.median(latencies), 2),
                "p95_ms": round(percentile(latencies, 0.95), 2),
                "p99_ms": round(percentile(latencies, 0.99), 2),
                "error_rate": round(errors / args.requests, 4),
                "requests_per_second": round(args.requests / elapsed, 2),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
