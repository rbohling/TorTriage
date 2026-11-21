# TorTriage
Client-side Tor performance measurements and fault-domain diagnostics.

## Shadow demo in Oracle VirtualBox

Run from the repository root on a host with Vagrant and Oracle VirtualBox.
The Ubuntu 24.04 guest uses 4 vCPUs and 6 GB of RAM. First provisioning needs
internet access and compiles Shadow v3.3.0 from source.

```powershell
vagrant up --provider=virtualbox
vagrant ssh -c "tortriage-demo baseline"
vagrant ssh -c "tortriage-demo constrained"
```

Open [the dashboard](http://127.0.0.1:8787). It refreshes automatically and
compares the latest reports from both scenarios. Each command runs four CLI
measurements through a private Shadow Tor client to a 512 KiB HTTP fixture.
In the constrained scenario, the fixture paces the HTTP response body at
512 Kbit/s using Shadow's simulated clock.
The CLI's per-sample timestamps and measurements use Shadow's simulated clock.
The dashboard's completion time uses the guest's wall clock. TorTriage applies
end-to-end thresholds and attributes each sample to its circuit through the
client's control port.

The topology uses one directory authority, four guard/middle candidates and two
exits from the pinned [Shadow Tor example](https://github.com/shadow/shadow/tree/v3.3.0/examples/docs/tor).
The target uses a fixed simulated IP so the demo can run without an exit DNS
server. The HTTP fixture and SOCKS listener exist inside Shadow. Only the
dashboard has a demo port forwarded to the Windows loopback interface.

The runner prints a guest directory under `/var/lib/tortriage/` for each run.
It contains `shadow.log` and per-process stdout/stderr under `shadow.data/hosts/`.
The latest reports are also available at
[the JSON endpoint](http://127.0.0.1:8787/api/results).
Run `vagrant halt` to stop the VM and keep its reports.

## Project scope and delivery constraints

- **Team:** 3 cybersecurity students
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
2. Report circuit attribution as verified only when the measurement's own stream is correlated to a circuit via the control port; otherwise report it as unverified with a reason.
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

### 4) Enable Tor's control port (for circuit attribution)

TorTriage authenticates with Tor's **control cookie**; passwords are not supported.
Add this to your `torrc` and restart Tor:

```
ControlPort 127.0.0.1:9051
CookieAuthentication 1
```

The user running TorTriage must be able to read Tor's `control_auth_cookie` file
(on Debian/Ubuntu, add your user to the `debian-tor` group). If the control port
cannot be used, TorTriage prints a warning with the reason and the fix, still
measures, and reports attribution as `unverified`.

### 5) Review output safely

- CLI output prints explicit unverified circuit attribution and end-to-end observations per run
- JSON report is written to `artifacts/tortriage-report.json` by default
- Treat report artifacts as sensitive operational metadata; avoid sharing raw files publicly

### Safety notes

- Use test targets you are authorized to access
- Avoid sending authenticated/personal traffic through measurement URLs
- Keep default Tor-only routing behavior (no direct-network fallback)

## Attribution accuracy and compatibility

The prototype attributes a measurement to a circuit **only with direct evidence**
from Tor's control port; otherwise it reports `unverified` and leaves relay fields
empty. Each measurement uses unique SOCKS credentials, which Tor isolates and
echoes in STREAM events. `CircuitAttributor` in `tor_control.py` subscribes to
STREAM and CIRC events before the measurement starts, matches streams by those
credentials, and uses a stream's `SUCCEEDED` event (not NEW or `SENTCONNECT`) for
its circuit ID. The circuit path comes from the BUILT event (or a snapshot taken at
start, or a live query). Without a reachable, authenticated control port the tool
sends no credentials, behaves as before, and reports `unverified` with the reason.
Attribution stays `unverified` when:

- no STREAM event carries the measurement's credentials (e.g. an older Tor),
- no matched stream succeeded, or matched streams succeeded on different circuits,
- the circuit path is unavailable or is not exactly three identified hops,
- the control connection was lost during the measurement.

Concurrent traffic through the same Tor client does not affect matching, because
only streams with this measurement's credentials are considered. Because Tor
isolates by SOCKS credentials, each measurement now builds or uses its own circuit
instead of sharing one across runs.

### Port auto-detection

With no port options, the CLI looks for a local Tor client itself, so system Tor
and Tor Browser both work:

1. It tries the control ports `9051` (system Tor) then `9151` (Tor Browser),
   authenticating with the control cookie.
2. It asks that Tor for its SOCKS listener, so the two ports always belong to the
   same Tor instance. Only loopback listeners are used.
3. If no control port is usable, it prints a warning with the reason and how to fix
   it, then probes SOCKS ports `9050` then `9150` with a SOCKS5 greeting.
   Measurements still run, but attribution stays `unverified`.

`--tor-proxy` and `--control-port` override detection. The control port is always
reached on `127.0.0.1` (there is no option to change that), and both
ports must be loopback-only. The Shadow demo passes `--tor-proxy` explicitly.

The simulated demo client is configured like a real user's Tor: `ControlPort
127.0.0.1:9051` with `CookieAuthentication 1`, on the client only (relays have no
control port). The demo prints how many runs were attributed to a circuit. The
`get_current_circuit()` compatibility API
still returns an unverified result without querying Tor: the newest built circuit is
not evidence of the measurement path.

Remaining limits: control-port event loss other than a dropped connection cannot be
detected, and a path identifies the circuit, not each relay's latency or capacity.

Tor's [STREAM event specification](https://spec.torproject.org/control-spec/replies.html#stream-status-changed)
provides a stream ID, attached circuit ID (0 means unattached), status, and optional
SOCKS credentials.

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

## Shadow integration in GitHub Actions

CI runs both demo scenarios directly on Ubuntu 24.04 using the same Shadow
configuration and CLI as the Vagrant guest. It checks four successful samples
per scenario, confirms that the constrained response reduces measured
throughput, and verifies the dashboard API. The workflow uploads JSON reports
and simulation logs as the `shadow-demo-results` artifact.
