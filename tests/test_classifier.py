from tortriage.classifier import classify_bottleneck, confidence
from tortriage.models import AggregatedMetrics, CircuitInfo, MeasurementResult


def test_confidence_levels() -> None:
    assert confidence(1) == "low"
    assert confidence(4) == "medium"
    assert confidence(8) == "high"


def test_classification_when_measurement_fails() -> None:
    label, conf, _ = classify_bottleneck(
        MeasurementResult(rtt_ms=None, throughput_mbps=None, sample_url="https://example.com"),
        CircuitInfo(),
        AggregatedMetrics(),
    )
    assert label == "local_or_tor_unavailable"
    assert conf == "low"


def test_classification_exit_congestion() -> None:
    label, _, _ = classify_bottleneck(
        MeasurementResult(rtt_ms=600.0, throughput_mbps=0.5, sample_url="https://example.com"),
        CircuitInfo(entry="a", middle="b", exit="c", source="control-port"),
        AggregatedMetrics(),
    )
    assert label == "exit_or_upstream_congestion"
