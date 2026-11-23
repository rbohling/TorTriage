"""Serve the Shadow dashboard and completed reports from a local Tor client."""

import fnmatch
import json
import math
import os
import stat
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


STATE = Path("/var/lib/tortriage")
HTML = Path(__file__).with_name("dashboard.html")
SCENARIOS = ("baseline", "constrained")
LIVE_DIR = Path(os.environ.get("TORTRIAGE_LIVE_DIR", str(Path.home() / "tortriage-live")))
LIVE_PATTERNS = ("report.json", "report-*.json", "live-*.json")
MAX_REPORT_BYTES = 2 * 1024 * 1024


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Non-finite JSON number: {value}")
    return number


def _read_report(path):
    """Read one stable, regular file without following a report symlink."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_REPORT_BYTES:
                return None
            content = source.read(MAX_REPORT_BYTES + 1)
            after = os.fstat(source.fileno())
        if len(content) > MAX_REPORT_BYTES or (
            before.st_size, before.st_mtime_ns
        ) != (after.st_size, after.st_mtime_ns):
            return None
        return json.loads(content, parse_constant=_reject_constant, parse_float=_finite_float), after
    except (OSError, UnicodeError, ValueError, RecursionError):
        return None


def _metric(value):
    if value is None:
        return True
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _valid_live_report(report):
    """Check the fields rendered by the dashboard; failed samples are valid."""
    if not isinstance(report, dict):
        return False
    summary, results = report.get("summary"), report.get("results")
    if not isinstance(summary, dict) or not isinstance(results, list):
        return False
    if type(summary.get("runs")) is not int or summary["runs"] != len(results) or not results:
        return False
    for field in ("avg_rtt_ms", "avg_throughput_mbps"):
        if field not in summary or not _metric(summary[field]):
            return False
    for result in results:
        if not isinstance(result, dict) or not isinstance(result.get("classification"), str):
            return False
        measurement, circuit = result.get("measurement"), result.get("circuit")
        if not isinstance(measurement, dict) or not isinstance(circuit, dict):
            return False
        for field in ("rtt_ms", "throughput_mbps"):
            if field not in measurement or not _metric(measurement[field]):
                return False
        if "sample_url" in measurement and not isinstance(measurement["sample_url"], str):
            return False
        if circuit.get("attribution") not in ("verified", "unverified"):
            return False
        # Older reports predate circuit_id, and unverified reports have no hops.
        for field in ("entry", "middle", "exit", "circuit_id", "attribution_reason"):
            value = circuit.get(field)
            if value is not None and not isinstance(value, str):
                return False
        if circuit["attribution"] == "verified" and not all(
            isinstance(circuit.get(field), str) and circuit[field].strip()
            for field in ("entry", "middle", "exit", "circuit_id")
        ):
            return False
    return True


def latest_live_report():
    """Find the newest completed report in the configured local directory."""
    candidates = []
    try:
        for path in LIVE_DIR.iterdir():
            if not any(fnmatch.fnmatchcase(path.name, pattern) for pattern in LIVE_PATTERNS):
                continue
            try:
                info = path.lstat()
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode):
                candidates.append((info.st_mtime_ns, path))
    except OSError:
        return None
    candidates.sort(key=lambda item: (item[0], item[1].name), reverse=True)
    for _, path in candidates:
        loaded = _read_report(path)
        if loaded is None:
            continue
        report, info = loaded
        if not _valid_live_report(report):
            continue
        try:
            saved_at = datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat()
        except (ValueError, OverflowError, OSError):
            continue
        successful = sum(
            sample["measurement"]["rtt_ms"] is not None
            and (sample["measurement"]["throughput_mbps"] or 0) > 0
            for sample in report["results"]
        )
        return {
            **report,
            "dashboard": {"report_name": path.name, "saved_at": saved_at, "successful": successful},
        }
    return None


def collect_reports():
    reports = {}
    for scenario in SCENARIOS:
        loaded = _read_report(STATE / f"{scenario}.json")
        reports[scenario] = loaded[0] if loaded is not None else None
    reports["live"] = latest_live_report()
    return reports


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.respond("text/html; charset=utf-8", HTML.read_bytes())
        elif self.path == "/api/results":
            self.respond("application/json", json.dumps(collect_reports(), allow_nan=False).encode("utf-8"))
        else:
            self.send_error(404)

    def respond(self, content_type, body):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def main():
    host = os.environ.get("TORTRIAGE_DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("TORTRIAGE_DASHBOARD_PORT", "8787"))
    with ThreadingHTTPServer((host, port), DashboardHandler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
