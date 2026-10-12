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
2. Correlate measurements with currently selected Tor circuit nodes (entry/middle/exit).
3. Flag the most likely bottleneck segment based on repeated degraded results.
4. Output a simple per-test report (CLI text and JSON) with:
   - timestamp
   - circuit fingerprints/nicknames (when available)
   - measured RTT/throughput
   - suspected bottleneck classification
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

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
tortriage --runs 4 --url https://check.torproject.org
```
