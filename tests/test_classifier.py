import unittest

from tortriage.classifier import classify_bottleneck, confidence
from tortriage.models import AggregatedMetrics, CircuitInfo, MeasurementResult


class ClassifierTests(unittest.TestCase):
    def test_repetition_does_not_establish_cause(self):
        for count in (1, 4, 8, 100):
            self.assertEqual(confidence(count), "low")

    def test_only_end_to_end_observations_are_classified(self):
        for circuit in (CircuitInfo(), CircuitInfo(entry="a", middle="b", exit="c")):
            for latency, throughput, expected in (
                (None, None, "measurement_unavailable"),
                (600, .5, "high_latency_and_low_throughput"),
                (600, 2, "high_latency"),
                (100, .5, "low_throughput"),
                (100, 2, "within_configured_thresholds"),
                (450, 1.2, "within_configured_thresholds"),
            ):
                with self.subTest(latency=latency, throughput=throughput, circuit=circuit):
                    label, conf, rationale = classify_bottleneck(
                        MeasurementResult(latency, throughput, "https://example.com"),
                        circuit, AggregatedMetrics(),
                    )
                    self.assertEqual(label, expected)
                    self.assertEqual(conf, "low")
                    self.assertIn("cannot locate a bottleneck", rationale)
