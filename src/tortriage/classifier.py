from __future__ import annotations

from .models import AggregatedMetrics, CircuitInfo, MeasurementResult

# Illustrative end-to-end thresholds, not calibrated per-relay baselines.
BASELINE_RTT_MS = 450
BASELINE_THROUGHPUT_MBPS = 1.2


def classify_bottleneck(
    measurement: MeasurementResult,
    circuit: CircuitInfo,
    aggregate: AggregatedMetrics,
) -> tuple[str, str, str]:
    # Neither circuit names nor repeated samples establish per-relay performance.
    limitation = " End-to-end measurements cannot locate a bottleneck or diagnose individual relays."
    if measurement.rtt_ms is None or measurement.throughput_mbps is None:
        return (
            "measurement_unavailable",
            "low",
            "Measurement failed through the configured Tor proxy or endpoint; cause undetermined." + limitation,
        )

    high_latency = measurement.rtt_ms > BASELINE_RTT_MS
    low_throughput = measurement.throughput_mbps < BASELINE_THROUGHPUT_MBPS
    if high_latency and low_throughput:
        label = "high_latency_and_low_throughput"
    elif high_latency:
        label = "high_latency"
    elif low_throughput:
        label = "low_throughput"
    else:
        label = "within_configured_thresholds"
    return (
        label,
        "low",
        "Observed end-to-end performance compared with illustrative fixed thresholds "
        f"({BASELINE_RTT_MS} ms time to first body chunk, {BASELINE_THROUGHPUT_MBPS} Mbps)."
        + limitation,
    )


def confidence(run_count: int) -> str:
    """Compatibility helper: repetition alone does not increase diagnostic certainty."""
    return "low"
