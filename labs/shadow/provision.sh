#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
test "$(dpkg --print-architecture)" = amd64 || {
  echo 'This Shadow demo requires an x86-64 Ubuntu guest.' >&2
  exit 1
}
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl git build-essential cmake pkg-config \
  libclang-dev libc6-dbg libglib2.0-dev libigraph-dev libopenblas0-serial \
  libssl-dev libevent-dev zlib1g-dev findutils netbase xz-utils util-linux \
  python3 python3-venv python3-yaml python3-networkx tor

# Shadow starts Tor inside the simulation; no public Tor daemon is needed.
systemctl disable --now tor.service tor@default.service
install -d -o vagrant -g vagrant /home/vagrant/shadow-lab
install -o vagrant -g vagrant -m 0755 /tmp/tortriage-shadow-guest-build.sh \
  /home/vagrant/shadow-lab/guest-build.sh
install -o vagrant -g vagrant -m 0755 /tmp/tortriage-shadow-demo.py \
  /home/vagrant/shadow-lab/demo.py
sudo --user=vagrant --set-home bash /home/vagrant/shadow-lab/guest-build.sh
