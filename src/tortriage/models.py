from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import mean


@dataclass(frozen=True)
class CircuitInfo:
    entry: str | None = None
    middle: str | None = None
    exit: str | None = None
    source: str = "unavailable"
    attribution: str = "unverified"
    attribution_reason: str = "No measurement-to-stream correlation was established."


@dataclass(frozen=True)
class MeasurementResult:
    rtt_ms: float | None
    throughput_mbps: float | None
    sample_url: str


@dataclass(frozen=True)
class RunResult:
    timestamp: str
    circuit: CircuitInfo
    measurement: MeasurementResult
    classification: str
    confidence: str
    rationale: str


@dataclass
class AggregatedMetrics:
    runs: list[RunResult] = field(default_factory=list)

    @property
    def avg_rtt_ms(self) -> float | None:
        values = [run.measurement.rtt_ms for run in self.runs if run.measurement.rtt_ms is not None]
        return round(mean(values), 2) if values else None

    @property
    def avg_throughput_mbps(self) -> float | None:
        values = [run.measurement.throughput_mbps for run in self.runs if run.measurement.throughput_mbps is not None]
        return round(mean(values), 4) if values else None


def now_utc_iso() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()
