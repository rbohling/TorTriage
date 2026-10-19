# TorTriage
Client-side Tor performance measurements and fault-domain diagnostics.

## Project scope and delivery constraints

- **Team:** 2 cybersecurity students
- **Timeline:** 8 weeks
- **Capacity:** ~2 hours/week each (32 total person-hours)
- **Primary stack:** Python
- **Test environment:** Linux VM running Tor Browser/Tor services locally

## Goal

Build a lightweight Tor network analyzer that helps identify likely bottlenecks in a local Tor path, including:

- Entry (guard) node issues
- Middle relay issues
- Exit node issues
- Local client-side or network saturation issues

## Minimal viable analyzer (MVP)

The first deliverable should prioritize practical diagnostics over full network-wide certainty:

1. Collect repeatable latency and throughput measurements from the local Tor client.
2. Report circuit attribution explicitly as unverified until measurement-to-stream correlation exists.
3. Flag observed end-to-end degradation without assigning a relay or local fault domain.
4. Output a simple per-test report (CLI text and JSON) with:
   - timestamp
   - circuit attribution status and reason (relay fields remain empty without evidence)
   - measured RTT/throughput
   - end-to-end performance classification
   - confidence score (low/medium/high)

## Suggested 8-week plan (2 hours/week)

1. **Week 1:** Define success criteria, pick Python libraries, set up Linux VM + Tor test workflow.
2. **Week 2:** Implement baseline measurement script (latency + download timing through Tor).
3. **Week 3:** Integrate Tor control-port circuit metadata collection.
4. **Week 4:** Build data model and store run results (JSON files).
5. **Week 5:** Implement bottleneck classification heuristics (entry/middle/exit/local).
6. **Week 6:** Add repeated-run aggregation and confidence scoring.
7. **Week 7:** Add report formatting (human-readable + JSON), run validation scenarios in VM.
8. **Week 8:** Final polish, documentation, and demo dataset/results.

## Practical implementation notes

- Keep dependencies small and common (e.g., `stem`, `requests`, standard library).
- Prefer deterministic, scripted tests in the Linux VM so results are reproducible.
- Start with CLI-only output; delay any GUI work unless time remains.
- Track known limitations (Tor path churn, noisy measurements, unavailable node metadata).
- Measurement traffic is Tor-only (`socks5h`), with direct-network fallback disabled.
- Measurement requests ignore environment proxy variables to avoid accidental non-Tor routing.

## Python artifacts included for the MVP

- `pyproject.toml` package metadata and CLI entrypoint (`tortriage`)
- `requirements.txt` direct dependency install list
- `src/tortriage/cli.py` CLI workflow for repeated tests and report generation
- `src/tortriage/measurements.py` Tor-proxied latency/throughput measurement
- `src/tortriage/tor_control.py` Tor control-port circuit metadata collection
- `src/tortriage/classifier.py` bottleneck classification heuristics and confidence scoring
- `src/tortriage/reporting.py` CLI and JSON report formatting/output
- `src/tortriage/models.py` shared run, circuit, and aggregation data models
- `tests/test_classifier.py` baseline tests for classification behavior

## Practical safe run (recommended)

Use a disposable Linux VM and a local Tor daemon so test traffic stays isolated from your normal browsing/session.

### 1) Start in an isolated environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 2) Confirm Tor is local-only before testing

Run these checks before you start measurements:

```bash
# Confirm Tor is listening on the expected ports
nc -zv 127.0.0.1 9050
nc -zv 127.0.0.1 9051

# Confirm those listeners are bound only to localhost
ss -ltn '( sport = :9050 or sport = :9051 )'
```

Expected result: listeners should show `127.0.0.1:9050` and `127.0.0.1:9051` (or `::1` for IPv6 localhost), **not** `0.0.0.0` or a public/private LAN IP.

If you see non-local bindings, fix your Tor config before testing. Do **not** expose Tor SOCKS or control ports publicly.

### 3) Run a low-impact baseline first

```bash
tortriage --runs 3 --delay-seconds 2 --timeout-seconds 20 --url https://check.torproject.org
```

This keeps request volume modest while validating your setup.

### 4) Optional: include control-port authentication

If your Tor control port requires a password:

```bash
tortriage --control-password 'your-password' --runs 4 --url https://check.torproject.org
```

### 5) Review output safely

- CLI output prints explicit unverified circuit attribution and end-to-end observations per run
- JSON report is written to `artifacts/tortriage-report.json` by default
- Treat report artifacts as sensitive operational metadata; avoid sharing raw files publicly

### Safety notes

- Use test targets you are authorized to access
- Avoid sending authenticated/personal traffic through measurement URLs
- Keep default Tor-only routing behavior (no direct-network fallback)

## Attribution accuracy and compatibility

The current prototype deliberately **does not attribute measurements to circuits**.
`circuit.attribution` is `unverified`, `attribution_reason` explains the missing
correlation, and relay fields are empty in CLI/JSON reports. Control-port options
remain accepted for CLI compatibility but are currently unused. The
`get_current_circuit()` compatibility API returns an unverified result without
querying Tor: the newest built circuit is not evidence of the measurement path.

Tor's [STREAM event specification](https://spec.torproject.org/control-spec/replies.html#stream-status-changed)
provides a stream ID, attached circuit ID (0 means unattached), status, and optional
SOCKS credentials. These can support attribution **when** the application first
subscribes to events and unambiguously correlates its actual SOCKS connections
(e.g., unique per-measurement SOCKS credentials). A future implementation must
track successful attachment rather than NEW/initial attachment, handle detach and
reattach, redirects/retries using multiple streams/circuits, drain asynchronous
events, and retain the relevant circuit paths before they disappear. Missing
identity fields, event loss, unsupported versions, control failures, or ambiguous
matches must leave attribution unverified. Matching only target or event timing
is insufficient when concurrent traffic uses the same Tor client. No stream
attachment or global Tor configuration changes are made by this fix.

Even verified stream-to-circuit mapping would identify a path, not measure each
relay's latency or capacity. Fixed thresholds now produce only `high_latency`,
`low_throughput`, `high_latency_and_low_throughput`, or
`within_configured_thresholds`; failed samples produce `measurement_unavailable`.
These replace the old speculative fault-domain labels. Consumers should update
label handling. Confidence stays low regardless of repetition. The legacy
`rtt_ms` field measures time to the first body chunk (including connection, TLS,
server, and buffering delays), not a network RTT. Throughput is a small HTTP
sample estimate, not a calibrated relay capacity measurement.

Offline regression checks (no Tor daemon or live HTTP measurements required):

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
