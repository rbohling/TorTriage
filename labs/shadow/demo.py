#!/usr/bin/env python3
"""Small Shadow demo; TorTriage traffic is confined to the simulated network."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import yaml

LAB = Path(__file__).resolve().parent
SHADOW = Path("/home/vagrant/.local/bin/shadow")
PYTHON = LAB / "venv/bin/python3"
EXAMPLE = LAB / "src/shadow/examples/docs/tor"


def create_run(mode):
    root = LAB / "results"
    root.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(tempfile.mkdtemp(prefix=f"{stamp}-{mode}-", dir=root))


def configure(mode, run):
    if mode == "smoke":
        config = {
            "general": {"stop_time": "10s", "model_unblocked_syscall_latency": True},
            "network": {"graph": {"type": "1_gbit_switch"}},
            "hosts": {
                "server": {"network_node_id": 0, "processes": [{
                    "path": "/usr/bin/python3", "args": "-m http.server 8080",
                    "start_time": "1s", "expected_final_state": "running"}]},
                "client": {"network_node_id": 0, "processes": [{
                    "path": "/usr/bin/curl", "args": "-fsS http://server:8080/",
                    "start_time": "3s"}]},
            },
        }
    else:
        shutil.copytree(EXAMPLE / "conf", run / "conf")
        shutil.copytree(EXAMPLE / "shadow.data.template", run / "shadow.data.template")
        config = yaml.safe_load((EXAMPLE / "shadow.yaml").read_text())
        config["general"]["seed"] = 1
        config["general"]["model_unblocked_syscall_latency"] = True
        # Change the whole modeled network, not a selected relay.
        if mode == "latency":
            graph = config["network"]["graph"]["inline"]
            if 'latency "50 ms"' not in graph:
                raise ValueError("Upstream example no longer matches the expected graph")
            config["network"]["graph"]["inline"] = graph.replace(
                'latency "50 ms"', 'latency "250 ms"', 1)
        webroot = run / "shadow.data.template/hosts/fileserver"
        webroot.mkdir(parents=True, exist_ok=True)
        (webroot / "payload.bin").write_bytes(
            b"TorTriage demo\n".ljust(512 * 1024, b"."))
        config["hosts"]["fileserver"]["processes"].append({
            "path": "/usr/bin/python3",
            "args": "-m http.server 8080 --bind 0.0.0.0",
            "start_time": 1, "expected_final_state": "running",
        })
        config["hosts"]["torclient"]["processes"].append({
            "path": str(PYTHON),
            "args": [
                "-m", "tortriage", "--url", "http://fileserver:8080/payload.bin",
                "--tor-proxy", "socks5h://127.0.0.1:9000",
                "--runs", "3", "--delay-seconds", "2", "--timeout-seconds", "30",
                "--json-output", "tortriage-report.json",
            ],
            "environment": {"PYTHONUNBUFFERED": "1"},
            "start_time": 1530,
        })
    with (run / "shadow.yaml").open("w") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)
    return config


def validate_report(report):
    results = report.get("results", [])
    if len(results) != 3:
        raise ValueError(f"Expected 3 measurements, received {len(results)}")
    for index, result in enumerate(results, 1):
        measurement = result.get("measurement", {})
        for key in ("rtt_ms", "throughput_mbps"):
            value = measurement.get(key)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Measurement {index}: {key} is unavailable or invalid")
        if measurement.get("sample_url") != "http://fileserver:8080/payload.bin":
            raise ValueError("Unexpected measurement target")
        if result.get("circuit", {}).get("attribution") != "unverified":
            raise ValueError("Unexpected relay-attribution status; review before presenting")


def execute(mode):
    run = create_run(mode)
    print(f"Running {mode}; logs and outputs: {run}", flush=True)
    try:
        configure(mode, run)
        command = [str(SHADOW)]
        if mode != "smoke":
            command += ["--template-directory", "shadow.data.template"]
        command += ["shadow.yaml"]
        env = os.environ.copy()
        env["PATH"] = "/home/vagrant/.local/bin:" + env.get("PATH", "")
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                    "http_proxy", "https_proxy", "all_proxy"):
            env.pop(key, None)
        with (run / "shadow.log").open("w") as stdout, (run / "shadow.stderr").open("w") as stderr:
            subprocess.run(command, cwd=run, env=env, stdout=stdout, stderr=stderr,
                           check=True, timeout=1800)
        if mode == "smoke":
            output = "\n".join(p.read_text(errors="replace") for p in
                               (run / "shadow.data/hosts/client").glob("*.stdout"))
            if "Directory listing" not in output:
                raise ValueError("Shadow HTTP smoke test did not return a directory listing")
            print("PASS: HTTP transfer completed inside Shadow.")
        else:
            path = run / "shadow.data/hosts/torclient/tortriage-report.json"
            report = json.loads(path.read_text())
            validate_report(report)
            shutil.copyfile(path, run / "tortriage-report.json")
            print("PASS: all 3 TorTriage measurements contain valid metrics.")
            print(json.dumps(report["summary"], indent=2))
            print("Relay attribution is unverified. This is a proof-of-concept demo.")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}\nInspect {run}; outputs have been preserved.", file=sys.stderr)
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["smoke", "baseline", "latency"])
    return execute(parser.parse_args().mode)


if __name__ == "__main__":
    raise SystemExit(main())
