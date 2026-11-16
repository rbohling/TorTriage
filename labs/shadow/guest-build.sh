#!/usr/bin/env bash
set -euo pipefail
LAB=/home/vagrant/shadow-lab
SHADOW_COMMIT=5a05740bad995b6dbb90b8a16effecf59eceee09
TGEN_COMMIT=816d68cd3d0ff7d0ec71e8bbbae24ecd6a636117
TORTRIAGE_COMMIT=de199379534765c2a8a7aaf8c6c1a62a3e160038
export PATH="/home/vagrant/.cargo/bin:/home/vagrant/.local/bin:$PATH"
export CARGO_BUILD_JOBS=2
mkdir -p "$LAB/src" "$LAB/logs" "$LAB/results"
exec > >(tee -a "$LAB/logs/provision.log") 2>&1

fetch_pinned() {
  local url=$1 dest=$2 revision=$3 current
  if [[ ! -d "$dest/.git" ]]; then
    if [[ -e "$dest" ]]; then
      echo "Refusing to replace existing non-repository path: $dest" >&2
      return 1
    fi
    git init "$dest"
    git -C "$dest" remote add origin "$url"
  fi
  current=$(git -C "$dest" rev-parse --verify HEAD 2>/dev/null || true)
  if [[ -n "$current" ]]; then
    [[ "$current" = "$revision" ]] || {
      echo "Existing checkout differs from the pinned revision: $dest" >&2
      return 1
    }
    git -C "$dest" diff --quiet
    git -C "$dest" diff --cached --quiet
  else
    git -C "$dest" fetch --depth 1 origin "$revision"
    git -C "$dest" checkout --detach FETCH_HEAD
  fi
}

fetch_pinned https://github.com/shadow/shadow.git "$LAB/src/shadow" "$SHADOW_COMMIT"
fetch_pinned https://github.com/shadow/tgen.git "$LAB/src/tgen" "$TGEN_COMMIT"
fetch_pinned https://github.com/rbohling/TorTriage.git "$LAB/src/tortriage" "$TORTRIAGE_COMMIT"

if ! command -v rustup >/dev/null 2>&1; then
  curl --proto '=https' --tlsv1.2 -fsS https://sh.rustup.rs -o "$LAB/rustup-init.sh"
  sh "$LAB/rustup-init.sh" -y --profile minimal --default-toolchain stable --no-modify-path
fi

cmake -S "$LAB/src/tgen" -B "$LAB/src/tgen/build" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/home/vagrant/.local
cmake --build "$LAB/src/tgen/build" --parallel 2
cmake --install "$LAB/src/tgen/build"
cd "$LAB/src/shadow"
./setup build --test --jobs 2
./setup test --jobs 2
./setup install
shadow --version

python3 -m venv "$LAB/venv"
"$LAB/venv/bin/python" -m pip install --editable "$LAB/src/tortriage"
cd "$LAB/src/tortriage"
"$LAB/venv/bin/python" -m unittest discover -s tests -v
{
  date --iso-8601=seconds
  printf 'Shadow commit: %s\nTGen commit: %s\nTorTriage commit: %s\n' \
    "$SHADOW_COMMIT" "$TGEN_COMMIT" "$TORTRIAGE_COMMIT"
  uname -a
  shadow --version
  tor --version
  rustc --version
  "$LAB/venv/bin/python" --version
  "$LAB/venv/bin/python" -m pip freeze
  dpkg-query -W tor
} > "$LAB/logs/versions.txt"

python3 "$LAB/demo.py" smoke
printf '\nProvisioning and smoke test passed. Run: python3 ~/shadow-lab/demo.py baseline\n'
