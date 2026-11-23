#!/usr/bin/env bash
# Update only the dashboard on an existing Chameleon TorTriage VM.
set -Eeuo pipefail
umask 022

if [[ $# -ne 1 || ! $1 =~ ^[[:xdigit:]]{40}$ ]]; then
    echo 'Usage: sudo bash update-dashboard.sh <full 40-character commit SHA>' >&2
    exit 2
fi
if [[ $EUID -ne 0 ]]; then
    echo 'Run this updater with sudo on the TorTriage VM.' >&2
    exit 1
fi

readonly REVISION=${1,,}
readonly SERVICE=tortriage-dashboard.service
readonly DEMO=/opt/tortriage/demo
readonly DROP_IN=/etc/systemd/system/tortriage-dashboard.service.d/live-dashboard.conf
readonly LIVE_DIR=/home/cc/tortriage-live
readonly PORT=8787
readonly PYTHON=/usr/bin/python3
readonly SOURCE=https://raw.githubusercontent.com/rbohling/TorTriage

for command in curl install mktemp systemctl ss flock cp mv; do
    command -v "$command" >/dev/null || { echo "Required command is missing: $command" >&2; exit 1; }
done
[[ -x $PYTHON ]] || { echo "Python is missing: $PYTHON" >&2; exit 1; }
[[ $(systemctl show --property=User --value "$SERVICE") == cc ]] || {
    echo 'Expected an existing tortriage-dashboard.service running as cc; leaving it unchanged.' >&2
    exit 1
}
for name in dashboard.py dashboard.html; do
    [[ -f $DEMO/$name ]] || { echo "Existing dashboard file is missing: $DEMO/$name" >&2; exit 1; }
done

exec 9>/run/lock/tortriage-dashboard-update.lock
flock -n 9 || { echo 'Another dashboard update is already running.' >&2; exit 1; }

stage=$(mktemp -d /var/tmp/tortriage-dashboard-update.XXXXXXXX)
backup=
changed=0
had_drop_in=0
trap 'rm -rf -- "$stage"' EXIT

# Copy to a sibling first, then rename so readers never see a partial file.
atomic_copy() {
    local source=$1 target=$2 mode=${3:-} pending
    pending=$(mktemp "${target}.update.XXXXXXXX") || return 1
    if [[ -n $mode ]]; then
        install -o root -g root -m "$mode" -- "$source" "$pending" || { rm -f -- "$pending"; return 1; }
    else
        cp -a --remove-destination -- "$source" "$pending" || { rm -f -- "$pending"; return 1; }
    fi
    mv -fT -- "$pending" "$target" || { rm -f -- "$pending"; return 1; }
}

on_error() {
    local status=$1 restored=1
    trap - ERR
    set +e
    if [[ $changed == 1 ]]; then
        echo "Dashboard update failed; restoring files from $backup." >&2
        systemctl stop "$SERVICE" || restored=0
        atomic_copy "$backup/dashboard.py" "$DEMO/dashboard.py" || restored=0
        atomic_copy "$backup/dashboard.html" "$DEMO/dashboard.html" || restored=0
        if [[ $had_drop_in == 1 ]]; then
            atomic_copy "$backup/live-dashboard.conf" "$DROP_IN" || restored=0
        else
            rm -f -- "$DROP_IN" || restored=0
        fi
        systemctl daemon-reload || restored=0
        systemctl restart "$SERVICE" || restored=0
        systemctl is-active --quiet "$SERVICE" || restored=0
        if [[ $restored == 1 ]]; then
            echo 'Previous dashboard restored and its service restarted.' >&2
        else
            echo "Rollback needs attention. Backup: $backup; inspect systemctl status $SERVICE." >&2
        fi
    else
        echo 'Dashboard update failed before replacing deployed files.' >&2
    fi
    exit "$status"
}
trap 'on_error "$?"' ERR

for name in dashboard.py dashboard.html; do
    curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
        --connect-timeout 15 --max-time 60 --retry 2 \
        "$SOURCE/$REVISION/demo/$name" --output "$stage/$name"
done
"$PYTHON" - "$stage/dashboard.py" "$stage/dashboard.html" <<'PY'
import ast
import sys
from pathlib import Path

ast.parse(Path(sys.argv[1]).read_text(encoding="utf-8"), filename="dashboard.py")
if 'id="live"' not in Path(sys.argv[2]).read_text(encoding="utf-8"):
    raise SystemExit('Downloaded dashboard is missing its live report panel')
PY

install -d -m 700 /opt/tortriage/dashboard-backups
backup=$(mktemp -d "/opt/tortriage/dashboard-backups/$(date -u +%Y%m%dT%H%M%SZ)-${REVISION:0:12}.XXXXXXXX")
cp -a -- "$DEMO/dashboard.py" "$backup/dashboard.py"
cp -a -- "$DEMO/dashboard.html" "$backup/dashboard.html"
if [[ -e $DROP_IN || -L $DROP_IN ]]; then
    cp -a -- "$DROP_IN" "$backup/live-dashboard.conf"
    had_drop_in=1
fi
cat >"$stage/live-dashboard.conf" <<CONF
[Service]
Environment="TORTRIAGE_DASHBOARD_HOST=127.0.0.1"
Environment="TORTRIAGE_DASHBOARD_PORT=$PORT"
Environment="TORTRIAGE_LIVE_DIR=$LIVE_DIR"
CONF

changed=1
systemctl stop "$SERVICE"
atomic_copy "$stage/dashboard.py" "$DEMO/dashboard.py" 644
atomic_copy "$stage/dashboard.html" "$DEMO/dashboard.html" 644
install -d -m 755 "$(dirname -- "$DROP_IN")"
atomic_copy "$stage/live-dashboard.conf" "$DROP_IN" 644
systemctl daemon-reload
systemctl restart "$SERVICE"

verified=0
for attempt in {1..10}; do
    if systemctl is-active --quiet "$SERVICE" && "$PYTHON" - "$PORT" <<'PY'
import json
import subprocess
import sys
from urllib.request import ProxyHandler, build_opener

port = int(sys.argv[1])
opener = build_opener(ProxyHandler({}))
with opener.open(f"http://127.0.0.1:{port}/", timeout=2) as response:
    html = response.read().decode("utf-8")
if 'id="live"' not in html:
    raise SystemExit('Live dashboard HTML was not served')
with opener.open(f"http://127.0.0.1:{port}/api/results", timeout=2) as response:
    reports = json.load(response)
if not isinstance(reports, dict) or not {"baseline", "constrained", "live"}.issubset(reports):
    raise SystemExit('Dashboard API is missing baseline, constrained, or live results')
listeners = subprocess.check_output(["ss", "-H", "-ltn", f"sport = :{port}"], text=True)
addresses = [line.split()[3] for line in listeners.splitlines() if line.strip()]
if not addresses or any(address != f"127.0.0.1:{port}" for address in addresses):
    raise SystemExit('Dashboard must listen only on 127.0.0.1')
PY
    then
        verified=1
        break
    fi
    sleep 1
done
if [[ $verified != 1 ]]; then
    echo 'Dashboard did not pass its startup checks.' >&2
    false
fi

echo "TORTRIAGE_DASHBOARD_UPDATED commit=$REVISION dashboard=127.0.0.1:$PORT live_dir=$LIVE_DIR backup=$backup"
