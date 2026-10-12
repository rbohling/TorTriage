import unittest

from tortriage.classifier import classify_bottleneck, confidence
from tortriage.models import AggregatedMetrics, CircuitInfo, MeasurementResult


class ClassifierTests(unittest.TestCase):
    def test_confidence_levels(self) -> None:
        self.assertEqual(confidence(1), "low")
        self.assertEqual(confidence(4), "medium")
        self.assertEqual(confidence(8), "high")

    def test_classification_when_measurement_fails(self) -> None:
        label, conf, _ = classify_bottleneck(
            MeasurementResult(rtt_ms=None, throughput_mbps=None, sample_url="https://example.com"),
            CircuitInfo(),
            AggregatedMetrics(),
        )
        self.assertEqual(label, "local_or_tor_unavailable")
        self.assertEqual(conf, "low")

    def test_classification_exit_congestion(self) -> None:
        label, _, _ = classify_bottleneck(
            MeasurementResult(rtt_ms=600.0, throughput_mbps=0.5, sample_url="https://example.com"),
            CircuitInfo(entry="a", middle="b", exit="c", source="control-port"),
            AggregatedMetrics(),
        )
        self.assertEqual(label, "exit_or_upstream_congestion")


if __name__ == "__main__":
    unittest.main()
