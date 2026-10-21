from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import AggregatedMetrics, RunResult


def to_json_report(aggregate: AggregatedMetrics) -> dict:
    return {
        "summary": {
            "runs": len(aggregate.runs),
            "avg_rtt_ms": aggregate.avg_rtt_ms,
            "avg_throughput_mbps": aggregate.avg_throughput_mbps,
        },
        "results": [asdict(result) for result in aggregate.runs],
    }


def write_json_report(path: Path, aggregate: AggregatedMetrics) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_json_report(aggregate), indent=2), encoding="utf-8")


def to_cli_text(run: RunResult) -> str:
    circuit = run.circuit
    measurement = run.measurement
    return (
        f"[{run.timestamp}] classification={run.classification} confidence={run.confidence}\n"
        f"  circuit_attribution={circuit.attribution}: {circuit.attribution_reason}\n"
        f"  entry={circuit.entry or 'n/a'} middle={circuit.middle or 'n/a'} exit={circuit.exit or 'n/a'}\n"
        f"  source={circuit.source} rtt_ms={measurement.rtt_ms} throughput_mbps={measurement.throughput_mbps}\n"
        f"  rationale={run.rationale}"
    )
