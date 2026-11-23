import importlib.util
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler, build_opener


spec = importlib.util.spec_from_file_location(
    "tortriage_dashboard", Path(__file__).resolve().parents[1] / "demo" / "dashboard.py"
)
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)


def sample_report():
    # This is the older CLI report shape: no demo metadata or circuit_id.
    return {
        "summary": {"runs": 1, "avg_rtt_ms": 250.0, "avg_throughput_mbps": 0.5},
        "results": [{
            "timestamp": "2026-11-23T12:00:00+00:00",
            "measurement": {
                "rtt_ms": 250.0,
                "throughput_mbps": 0.5,
                "sample_url": "https://check.torproject.org/",
            },
            "circuit": {
                "entry": None, "middle": None, "exit": None,
                "attribution": "unverified",
                "attribution_reason": "No measurement-to-stream correlation was established.",
            },
            "classification": "low_throughput",
            "confidence": "low",
            "rationale": "End-to-end observation.",
        }],
    }


class DashboardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / "shadow"
        self.live = self.root / "live"
        self.state.mkdir()
        self.live.mkdir()
        for name, value in (("STATE", self.state), ("LIVE_DIR", self.live)):
            setting = patch.object(dashboard, name, value)
            setting.start()
            self.addCleanup(setting.stop)

    def write_live(self, name="report.json", report=None, mtime=1_000):
        path = self.live / name
        path.write_text(json.dumps(sample_report() if report is None else report))
        os.utime(path, ns=(mtime * 1_000_000_000, mtime * 1_000_000_000))
        return path

    def test_absent_live_directory_preserves_shadow_contract(self):
        baseline = {**sample_report(), "demo": {"scenario": "baseline", "successful": 1}}
        constrained = {**sample_report(), "demo": {"scenario": "constrained", "successful": 1}}
        (self.state / "baseline.json").write_text(json.dumps(baseline))
        (self.state / "constrained.json").write_text(json.dumps(constrained))
        self.live.rmdir()
        self.assertEqual(dashboard.collect_reports(), {
            "baseline": baseline, "constrained": constrained, "live": None,
        })

    def test_older_raw_report_gets_server_metadata(self):
        report = sample_report()
        self.write_live(report=report)
        loaded = dashboard.latest_live_report()
        self.assertEqual(loaded["summary"], report["summary"])
        self.assertEqual(loaded["results"], report["results"])
        self.assertNotIn("demo", loaded)
        self.assertNotIn("circuit_id", loaded["results"][0]["circuit"])
        self.assertEqual(loaded["dashboard"], {
            "report_name": "report.json",
            "saved_at": datetime.fromtimestamp(1_000, timezone.utc).isoformat(),
            "successful": 1,
        })

    def test_latest_of_all_supported_filename_patterns_is_selected(self):
        for index, name in enumerate(("report.json", "report-20261123-10.json", "live-20261123-11.json")):
            self.write_live(name, mtime=1_000 + index)
            self.assertEqual(dashboard.latest_live_report()["dashboard"]["report_name"], name)
        self.write_live("unrelated.json", mtime=2_000)
        nested = self.live / "nested"
        nested.mkdir()
        (nested / "report.json").write_text(json.dumps(sample_report()))
        self.assertEqual(
            dashboard.latest_live_report()["dashboard"]["report_name"], "live-20261123-11.json"
        )

    def test_partial_and_malformed_newest_files_fall_back_then_completed_write_appears(self):
        self.write_live()
        partial = self.live / "report-new.json"
        partial.write_text('{"summary":')
        self.assertEqual(dashboard.latest_live_report()["dashboard"]["report_name"], "report.json")
        partial.write_text(json.dumps({"summary": {}, "results": []}))
        self.assertEqual(dashboard.latest_live_report()["dashboard"]["report_name"], "report.json")
        partial.write_text(json.dumps(sample_report()))
        self.assertEqual(dashboard.latest_live_report()["dashboard"]["report_name"], partial.name)

    def test_unreadable_or_disappearing_newest_file_falls_back(self):
        self.write_live()
        newest = self.write_live("live-new.json", mtime=2_000)
        real_open = os.open
        for error in (PermissionError("denied"), FileNotFoundError("removed")):
            def open_file(path, flags):
                if Path(path) == newest:
                    raise error
                return real_open(path, flags)

            with self.subTest(error=type(error).__name__), patch.object(dashboard.os, "open", side_effect=open_file):
                self.assertEqual(dashboard.latest_live_report()["dashboard"]["report_name"], "report.json")

    def test_symlinks_directories_and_fifos_are_not_read(self):
        self.write_live()
        outside = self.root / "private.json"
        outside.write_text(json.dumps(sample_report()))
        (self.live / "live-link.json").symlink_to(outside)
        (self.live / "report-directory.json").mkdir()
        os.mkfifo(self.live / "report-pipe.json")
        self.assertEqual(dashboard.latest_live_report()["dashboard"]["report_name"], "report.json")
        self.assertIsNone(dashboard._read_report(self.live / "live-link.json"))
        self.assertIsNone(dashboard._read_report(self.live / "report-pipe.json"))

    def test_latest_completed_failed_measurement_is_displayed(self):
        self.write_live()
        failed = sample_report()
        failed["summary"].update(avg_rtt_ms=None, avg_throughput_mbps=None)
        failed["results"][0]["measurement"].update(rtt_ms=None, throughput_mbps=None)
        failed["results"][0]["classification"] = "measurement_unavailable"
        self.write_live("live-failed.json", failed, mtime=2_000)
        loaded = dashboard.latest_live_report()
        self.assertEqual(loaded["dashboard"]["report_name"], "live-failed.json")
        self.assertEqual(loaded["dashboard"]["successful"], 0)
        self.assertIsNone(loaded["summary"]["avg_rtt_ms"])

    def test_verified_report_includes_renderable_path_and_circuit_id(self):
        report = sample_report()
        report["results"][0]["circuit"].update(
            attribution="verified", circuit_id="42",
            entry="$AAAAAAAA~guard", middle="$BBBBBBBB~middle", exit="$CCCCCCCC~exit",
        )
        self.write_live(report=report)
        loaded = dashboard.latest_live_report()
        self.assertEqual(loaded["results"][0]["circuit"], report["results"][0]["circuit"])
        self.assertEqual(loaded["dashboard"]["successful"], 1)

    def test_incomplete_verified_path_falls_back_to_previous_completed_report(self):
        self.write_live()
        for field in ("entry", "middle", "exit", "circuit_id"):
            for value in (None, "", "   "):
                report = sample_report()
                circuit = report["results"][0]["circuit"]
                circuit.update(
                    attribution="verified", circuit_id="42",
                    entry="$AAAAAAAA~guard", middle="$BBBBBBBB~middle", exit="$CCCCCCCC~exit",
                )
                circuit[field] = value
                with self.subTest(field=field, value=value):
                    self.write_live("live-incomplete.json", report, mtime=2_000)
                    self.assertEqual(dashboard.latest_live_report()["dashboard"]["report_name"], "report.json")

    def test_nonstring_sample_targets_are_rejected(self):
        self.write_live()
        for value in (None, 12, ["https://example.com"], {"url": "https://example.com"}):
            report = sample_report()
            report["results"][0]["measurement"]["sample_url"] = value
            with self.subTest(value=value):
                self.write_live("live-invalid-target.json", report, mtime=2_000)
                self.assertEqual(dashboard.latest_live_report()["dashboard"]["report_name"], "report.json")

    def test_nonfinite_and_invalid_rendered_fields_are_skipped(self):
        self.write_live()
        variants = []
        for value in (float("nan"), float("inf"), True, -1, "fast"):
            report = sample_report()
            report["summary"]["avg_throughput_mbps"] = value
            variants.append(report)
        for field, value in (("rtt_ms", float("inf")), ("throughput_mbps", True)):
            report = sample_report()
            report["results"][0]["measurement"][field] = value
            variants.append(report)
        report = sample_report()
        report["summary"]["runs"] = 2
        variants.append(report)
        report = sample_report()
        report["results"][0]["classification"] = {"bad": "shape"}
        variants.append(report)
        report = sample_report()
        report["results"][0]["circuit"]["entry"] = ["bad hop"]
        variants.append(report)
        for index, report in enumerate(variants):
            with self.subTest(index=index):
                self.write_live("live-invalid.json", report, mtime=2_000)
                self.assertEqual(dashboard.latest_live_report()["dashboard"]["report_name"], "report.json")

    def test_partial_shadow_file_does_not_hide_other_results(self):
        (self.state / "baseline.json").write_text('{"results":')
        constrained = sample_report()
        (self.state / "constrained.json").write_text(json.dumps(constrained))
        self.write_live()
        reports = dashboard.collect_reports()
        self.assertIsNone(reports["baseline"])
        self.assertEqual(reports["constrained"], constrained)
        self.assertIsNotNone(reports["live"])

    def test_nonfinite_exponents_in_extra_fields_do_not_break_api(self):
        self.write_live()
        newer = self.live / "live-overflow.json"
        content = json.dumps(sample_report())
        newer.write_text(content[:-1] + ', "extra": 1e9999}')
        reports = dashboard.collect_reports()
        self.assertEqual(reports["live"]["dashboard"]["report_name"], "report.json")
        json.dumps(reports, allow_nan=False)

    def test_http_results_are_json_and_request_cannot_choose_a_file(self):
        self.write_live()
        server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.DashboardHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        opener = build_opener(ProxyHandler({}))
        address = f"http://127.0.0.1:{server.server_port}"
        try:
            with patch.object(dashboard.DashboardHandler, "log_message"):
                with opener.open(address + "/api/results", timeout=5) as response:
                    self.assertEqual(response.headers["Content-Type"], "application/json")
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertEqual(json.load(response), dashboard.collect_reports())
                with self.assertRaises(HTTPError) as rejected:
                    opener.open(address + "/api/results?path=/etc/passwd", timeout=5)
                self.assertEqual(rejected.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_main_uses_requested_bind_without_changing_vagrant_default(self):
        for environment, expected in (
            ({}, ("0.0.0.0", 8787)),
            ({"TORTRIAGE_DASHBOARD_HOST": "127.0.0.1", "TORTRIAGE_DASHBOARD_PORT": "0"}, ("127.0.0.1", 0)),
        ):
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True), \
                    patch.object(dashboard, "ThreadingHTTPServer") as server:
                dashboard.main()
                server.assert_called_once_with(expected, dashboard.DashboardHandler)
                server.return_value.__enter__.return_value.serve_forever.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
