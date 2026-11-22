#!/usr/bin/env bash
set -euo pipefail

scenario=${1:-baseline}
case "$scenario" in
    baseline) bytes_per_second=0 ;;
    constrained) bytes_per_second=64000 ;;
    *) echo 'Usage: tortriage-demo [baseline|constrained]' >&2; exit 2 ;;
esac

state=/var/lib/tortriage
source=/opt/tortriage/shadow/examples/docs/tor
run_dir=$(mktemp -d "$state/$scenario.XXXXXXXX")
chmod 750 "$run_dir"
cd "$run_dir"
cp -r "$source/conf" "$source/shadow.data.template" .
chmod -R u+rwX,go-rwx shadow.data.template
sed -i '/^ControlPort /d' conf/tor.common.torrc
# Only the client gets a control port, configured as a real user's Tor should be:
# loopback-only with cookie authentication.
printf 'ControlPort 127.0.0.1:9051\nCookieAuthentication 1\n' >> shadow.data.template/hosts/torclient/torrc
mkdir fixture
truncate -s 524288 fixture/payload.bin
sed "s/@BYTES_PER_SECOND@/$bytes_per_second/" /opt/tortriage/demo/shadow.yaml > shadow.yaml

echo "Running $scenario in Shadow. Logs: $run_dir"
simulation_status=0
shadow --template-directory shadow.data.template shadow.yaml > shadow.log 2>&1 || simulation_status=$?
client=shadow.data/hosts/torclient
report="$client/tortriage-report.json"
if [[ $simulation_status -ne 0 || ! -s "$report" ]]; then
    tail -n 20 shadow.log >&2
    echo "Shadow did not complete with a CLI report. Inspect $run_dir." >&2
    exit 1
fi

for output in "$client"/python*.stdout; do
    [[ ! -f "$output" ]] || cat "$output"
done
for output in "$client"/python*.stderr; do
    [[ ! -s "$output" ]] || cat "$output" >&2
done
python3 - "$report" "$scenario" "$run_dir" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

report, scenario, run_dir = sys.argv[1:]
report = json.loads(Path(report).read_text())
successful = sum(
    result["measurement"]["rtt_ms"] is not None
    and (result["measurement"]["throughput_mbps"] or 0) > 0
    for result in report["results"]
)
attributed = sum(result["circuit"]["attribution"] == "verified" for result in report["results"])
report["demo"] = {
    "scenario": scenario,
    "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "successful": successful,
    "attributed": attributed,
    "run_id": Path(run_dir).name,
}
staged = Path(run_dir) / "dashboard-report.json"
staged.write_text(json.dumps(report, indent=2), encoding="utf-8")
latest = Path(run_dir).parent / f"{scenario}.json"
staged.replace(latest)
print(f"{successful}/{len(report['results'])} successful measurements, {attributed} attributed to a circuit. Dashboard report: {latest}")
sys.exit(0 if successful == len(report["results"]) == 4 else 1)
PY
