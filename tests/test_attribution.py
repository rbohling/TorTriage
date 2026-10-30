import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tortriage.cli import main
from tortriage.models import MeasurementResult
from tortriage.tor_control import get_current_circuit


class AttributionTests(unittest.TestCase):
    def test_snapshot_never_claims_a_measurement_path(self):
        # This compatibility API must not select even the newest built circuit.
        with patch("stem.control.Controller.from_port") as connect:
            circuit = get_current_circuit()
        connect.assert_not_called()
        self.assertEqual(circuit.attribution, "unverified")
        self.assertIsNone(circuit.entry)
        self.assertIsNone(circuit.middle)
        self.assertIsNone(circuit.exit)

    def test_cli_and_json_explicitly_report_unverified_for_every_run(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            args = SimpleNamespace(runs=2, delay_seconds=0, timeout_seconds=1,
                                   url="https://example.com", json_output=str(output))
            with patch("tortriage.cli.parse_args", return_value=args), \
                 patch("tortriage.cli.run_measurement", side_effect=[
                     MeasurementResult(600, .5, args.url),
                     MeasurementResult(None, None, args.url),
                 ]) as measure, patch("builtins.print") as display:
                self.assertEqual(main(), 0)
            self.assertEqual(measure.call_count, 2)
            report = json.loads(output.read_text())
            for run in report["results"]:
                circuit = run["circuit"]
                self.assertEqual(circuit["attribution"], "unverified")
                self.assertTrue(circuit["attribution_reason"])
                self.assertIsNone(circuit["entry"])
                self.assertIsNone(circuit["exit"])
                self.assertEqual(run["confidence"], "low")
            for call in display.call_args_list[:2]:
                self.assertIn("circuit_attribution=unverified", call.args[0])
