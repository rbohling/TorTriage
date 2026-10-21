from __future__ import annotations

import argparse
import time
from pathlib import Path

from .classifier import classify_bottleneck
from .measurements import run_measurement
from .models import AggregatedMetrics, CircuitInfo, RunResult, now_utc_iso
from .reporting import to_cli_text, write_json_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tor bottleneck triage analyzer")
    parser.add_argument("--url", default="https://check.torproject.org", help="URL sampled through Tor")
    parser.add_argument("--runs", type=int, default=4, help="Number of repeated measurements")
    parser.add_argument("--delay-seconds", type=float, default=1.0, help="Delay between runs")
    parser.add_argument("--timeout-seconds", type=float, default=15.0, help="Request timeout in seconds")
    parser.add_argument("--control-host", default="127.0.0.1", help="Tor control host")
    parser.add_argument("--control-port", type=int, default=9051, help="Tor control port")
    parser.add_argument("--control-password", default=None, help="Tor control password")
    parser.add_argument("--json-output", default="artifacts/tortriage-report.json", help="JSON report path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runs = max(args.runs, 1)
    aggregate = AggregatedMetrics()

    for idx in range(runs):
        circuit = CircuitInfo(source="measurement-stream-not-correlated")
        measurement = run_measurement(args.url, timeout_seconds=args.timeout_seconds)
        classification, confidence, rationale = classify_bottleneck(measurement, circuit, aggregate)

        run = RunResult(
            timestamp=now_utc_iso(),
            circuit=circuit,
            measurement=measurement,
            classification=classification,
            confidence=confidence,
            rationale=rationale,
        )
        aggregate.runs.append(run)
        print(to_cli_text(run))
        if idx != runs - 1:
            time.sleep(max(args.delay_seconds, 0.0))

    write_json_report(Path(args.json_output), aggregate)
    print(f"\nJSON report written to {args.json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
