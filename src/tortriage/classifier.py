from __future__ import annotations

from .models import AggregatedMetrics, CircuitInfo, MeasurementResult

BASELINE_RTT_MS = 450
BASELINE_THROUGHPUT_MBPS = 1.2


def classify_bottleneck(
    measurement: MeasurementResult,
    circuit: CircuitInfo,
    aggregate: AggregatedMetrics,
) -> tuple[str, str, str]:
    if measurement.rtt_ms is None or measurement.throughput_mbps is None:
        return (
            "local_or_tor_unavailable",
            "low",
            "Measurement failed through configured Tor proxy or endpoint.",
        )

    avg_rtt = aggregate.avg_rtt_ms or measurement.rtt_ms
    avg_tp = aggregate.avg_throughput_mbps or measurement.throughput_mbps

    high_rtt = measurement.rtt_ms > BASELINE_RTT_MS
    low_tp = measurement.throughput_mbps < BASELINE_THROUGHPUT_MBPS

    if high_rtt and low_tp:
        if not circuit.exit:
            return (
                "local_client_or_network",
                confidence(len(aggregate.runs) + 1),
                "High latency and low throughput with missing exit metadata.",
            )
        return (
            "exit_or_upstream_congestion",
            confidence(len(aggregate.runs) + 1),
            "High latency plus low throughput suggests exit segment congestion.",
        )

    if high_rtt and measurement.throughput_mbps >= avg_tp:
        return (
            "middle_relay_path_latency",
            confidence(len(aggregate.runs) + 1),
            "Latency spike without throughput collapse suggests middle relay path delay.",
        )

    if low_tp and measurement.rtt_ms <= avg_rtt:
        return (
            "entry_guard_or_local_saturation",
            confidence(len(aggregate.runs) + 1),
            "Throughput drop without RTT spike suggests guard or local saturation.",
        )

    return (
        "no_clear_bottleneck",
        confidence(len(aggregate.runs) + 1),
        "Observed metrics remain within baseline bounds.",
    )


def confidence(run_count: int) -> str:
    if run_count >= 8:
        return "high"
    if run_count >= 4:
        return "medium"
    return "low"
