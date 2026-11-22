from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .classifier import classify_bottleneck
from .discovery import CONTROL_PORTS, LOOPBACK_HOST, SOCKS_PORTS, discover_socks_proxy
from .measurements import DEFAULT_TOR_PROXY, run_measurement
from .models import AggregatedMetrics, RunResult, now_utc_iso
from .reporting import to_cli_text, write_json_report
from .tor_control import CircuitAttributor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tor bottleneck triage analyzer")
    parser.add_argument("--url", default="https://check.torproject.org", help="URL sampled through Tor")
    parser.add_argument("--runs", type=int, default=4, help="Number of repeated measurements")
    parser.add_argument("--delay-seconds", type=float, default=1.0, help="Delay between runs")
    parser.add_argument("--timeout-seconds", type=float, default=15.0, help="Request timeout in seconds")
    parser.add_argument("--control-port", type=int, default=None, help=f"Tor control port (default: try {', '.join(map(str, CONTROL_PORTS))})")
    parser.add_argument("--tor-proxy", default=None, help=("SOCKS5 hostname proxy used for measurements "f"(default: detected via the control port, else probe {', '.join(map(str, SOCKS_PORTS))})"))
    parser.add_argument("--json-output", default="artifacts/tortriage-report.json", help="JSON report path")
    return parser.parse_args()


def _note(message: str) -> None:
    sys.stderr.write(f"{message}\n")


ENABLE_CONTROL_PORT_HELP = (
    "  Add these lines to your torrc and restart Tor:\n"
    "    ControlPort 127.0.0.1:9051\n"
    "    CookieAuthentication 1"
)
COOKIE_ACCESS_HELP = (
    "  TorTriage authenticates with Tor's control cookie (no password). Make sure the\n"
    "  user running TorTriage can read Tor's control_auth_cookie file (on Debian/Ubuntu,\n"
    "  add your user to the debian-tor group), and that CookieAuthentication is 1 in your torrc."
)


def warn_control_port_unavailable(attributor: CircuitAttributor) -> None:
    _note(
        "WARNING: Tor's control port could not be used, so measurements will NOT be "
        "attributed to a circuit (attribution stays unverified)."
    )
    _note(f"  Reason: {attributor.unavailable_reason}")
    _note(COOKIE_ACCESS_HELP if attributor.auth_failed else ENABLE_CONTROL_PORT_HELP)


def select_proxy(explicit: str | None, attributor: CircuitAttributor) -> str:
    """Prefer the user's choice, then the SOCKS port of the Tor behind the control port, then a probe."""
    if explicit:
        return explicit
    if attributor.socks_proxy:
        _note(f"Tor SOCKS proxy {attributor.socks_proxy} (reported by control port {attributor.port})")
        return attributor.socks_proxy
    probed = discover_socks_proxy()
    if probed:
        _note(f"Tor SOCKS proxy {probed} (detected by probing)")
        return probed
    _note(f"No Tor SOCKS listener found on {LOOPBACK_HOST}; trying {DEFAULT_TOR_PROXY}. Is Tor running?")
    return DEFAULT_TOR_PROXY


def main() -> int:
    args = parse_args()
    runs = max(args.runs, 1)
    aggregate = AggregatedMetrics()
    control_ports = (args.control_port,) if args.control_port else CONTROL_PORTS

    with CircuitAttributor(control_ports) as attributor:
        if not attributor.available:
            warn_control_port_unavailable(attributor)
        else:
            _note(f"Using Tor control port {LOOPBACK_HOST}:{attributor.port}")
        tor_proxy = select_proxy(args.tor_proxy, attributor)
        for idx in range(runs):
            trace = attributor.begin()
            measurement = run_measurement(
                args.url,
                timeout_seconds=args.timeout_seconds,
                tor_proxy=tor_proxy,
                socks_credentials=trace.credentials,
            )
            circuit = attributor.resolve(trace)
            classification, confidence, rationale = classify_bottleneck(measurement, circuit, aggregate)

            run = RunResult(
                timestamp=now_utc_iso(),
                circuit=circuit,
                measurement=measurement,
                classification=classification,
                confidence=confidence,
                rationale=rationale,
            )
            aggregate.runs.append(run)
            print(to_cli_text(run))
            if idx != runs - 1:
                time.sleep(max(args.delay_seconds, 0.0))

    write_json_report(Path(args.json_output), aggregate)
    print(f"\nJSON report written to {args.json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
