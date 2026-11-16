#!/usr/bin/env bash
set -euo pipefail

checkout=/vagrant
demo_user=vagrant
if [[ ${1:-} == --ci ]]; then
    checkout=$PWD
    demo_user=${SUDO_USER:?Run CI provisioning with sudo}
fi

export DEBIAN_FRONTEND=noninteractive
systemctl mask tor.service tor@default.service
apt-get update
apt-get install -y --no-install-recommends build-essential ca-certificates curl git cmake pkg-config \
    libclang-dev libc6-dbg libglib2.0-dev python3-venv tor

root=/opt/tortriage
shadow_source="$root/shadow"
if [[ ! -d "$shadow_source/.git" ]]; then
    git clone --depth 1 --branch v3.3.0 https://github.com/shadow/shadow.git "$shadow_source"
fi
if [[ ! -x /usr/local/bin/shadow ]]; then
    if [[ ! -x /root/.cargo/bin/rustup ]]; then
        curl -fsSL https://sh.rustup.rs | sh -s -- -y --default-toolchain none
    fi
    export PATH="/root/.cargo/bin:$PATH"
    export RUSTUP_TOOLCHAIN=1.100.0
    rustup toolchain install "$RUSTUP_TOOLCHAIN" --profile minimal
    cd "$shadow_source"
    ./setup build --prefix /usr/local
    ./setup install
    ldconfig
fi

python3 -m venv --copies "$root/venv"
cp -r "$checkout"/{src,pyproject.toml,README.md} "$root/"
"$root/venv/bin/pip" install "$root"
install -d "$root/demo"
install -m 644 "$checkout"/demo/{dashboard.py,dashboard.html,fixture.py,shadow.yaml} "$root/demo/"
install -m 755 "$checkout/demo/run.sh" /usr/local/bin/tortriage-demo
ln -sfn "$root/venv/bin/tortriage" /usr/local/bin/tortriage
install -o "$demo_user" -g "$(id -gn "$demo_user")" -d /var/lib/tortriage
if [[ ${1:-} != --ci ]]; then
    install -m 644 "$checkout/demo/tortriage-dashboard.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable tortriage-dashboard.service
    systemctl restart tortriage-dashboard.service
fi
