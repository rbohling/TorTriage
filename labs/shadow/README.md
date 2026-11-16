# TorTriage demo with Vagrant and Shadow

One Ubuntu 24.04 x86-64 VM runs Shadow 3.3.0, Tor, TGen, and TorTriage.
This is a small proof of concept for future research. Vagrant uses a
preinstalled Ubuntu box, so no ISO installation is required.

**Status: locally checked, not runtime-verified.** On 2026-11-16, Vagrant
configuration validation, Ruby/Python/PowerShell syntax checks, nine report
validation cases, and shell-file LF line-ending checks passed. Bash syntax
checking was blocked by the execution environment. VirtualBox's command
interface still returns E_ACCESSDENIED from the automation session, so no
successful VM start, Linux provisioning, Shadow build, or simulation is claimed.

## Start from Windows PowerShell

Vagrant and VirtualBox must be installed. From this directory:

```powershell
.\Start-Demo.ps1
```

The launcher checks VirtualBox access, validates the configuration, provisions
the VM, and runs the baseline. Use `-Mode both` to run baseline and latency.
It stops on failure and never deletes an existing VM. Run it in your normal
PowerShell session. The equivalent individual commands are:

```powershell
vagrant validate
vagrant up --provider=virtualbox
vagrant ssh -c 'python3 ~/shadow-lab/demo.py baseline'
```

Defaults: 2 vCPUs and 6 GiB RAM. Leave enough RAM for Windows. To change the
allocation before starting, set SHADOW_VM_MEMORY (MiB) and SHADOW_VM_CPUS:

```powershell
$env:SHADOW_VM_MEMORY = '8192'
$env:SHADOW_VM_CPUS = '4'
```

The selected box is bento/ubuntu-24.04 version 202510.26.0, found in this host's
cache when checked. Other hosts download it. Provisioning needs Internet access
for Ubuntu packages, GitHub, Rust, and Python dependencies. Compiling Shadow
can take a while; compiler activity is normal.

Vagrant creates a new project VM; no existing VM name or UUID is referenced.
Keep this directory's .vagrant folder to manage the same VM. Networking is NAT
with SSH bound to host loopback. Shared folders are disabled; provisioning
files are uploaded over SSH.

## Automated setup

1. Install guest build dependencies and Tor.
2. Fetch pinned Shadow, TGen, and TorTriage source revisions.
3. Build TGen and Shadow and run Shadow's default test suite.
4. Install TorTriage in a Python virtual environment and run its unit tests.
5. Run an HTTP smoke test inside Shadow.

Setup stops on failure. After resolving a failed dependency download, retry
with `vagrant provision`. Existing checkouts are preserved; a different commit
causes provisioning to stop. Logs are in ~/shadow-lab/logs/provision.log.

## Demonstration

```powershell
# Baseline: 3 HTTP measurements through the simulated Tor client.
vagrant ssh -c 'python3 ~/shadow-lab/demo.py baseline'

# Same topology and seed, with modeled link latency raised from 50 to 250 ms.
vagrant ssh -c 'python3 ~/shadow-lab/demo.py latency'

# Open a shell if needed.
vagrant ssh
```

The runner adapts Shadow's official small Tor example: one authority, four
ordinary relays, two exits, a Tor client, a direct TGen client, and a file server.
These are simulated hosts inside one VM. TGen background traffic is retained.
TorTriage runs on the simulated Tor client at simulated second 1530 and fetches
a 512 KiB HTTP fixture through that client's SOCKS port 9000.

The simulation ends at 30 simulated minutes, not necessarily 30 wall-clock
minutes. Each run has a 30-minute wall-time limit. All demo traffic is confined
to Shadow's simulated network; it does not measure the public Tor network.

A run passes only when Shadow exits successfully and all 3 TorTriage
measurements have finite, positive latency and throughput values. A JSON file
alone is not treated as success. Each run has a fresh directory under
~/shadow-lab/results/, preserving earlier reports, simulation configuration,
and host logs. Actual dependency versions are recorded in logs/versions.txt.

View report files from PowerShell:

```powershell
vagrant ssh -c 'find ~/shadow-lab/results -maxdepth 2 -name tortriage-report.json -print -exec cat {} \;'
```

To copy results with the Windows OpenSSH scp command, if installed:

```powershell
vagrant ssh-config | Set-Content -Encoding ascii .\ssh-config
scp -F .\ssh-config -r default:/home/vagrant/shadow-lab/results .\results
```

## What the demo establishes

Show the baseline report and compare it with the increased-latency report.
Do not promise a particular classifier label: the label depends on measurements
and current thresholds. The latency scenario changes the whole modeled network,
not one selected relay.

TorTriage's rtt_ms field measures time to the first received body chunk,
including connection setup; it is not a ping RTT. Throughput uses a short
512 KiB sample. Classifier confidence remains low, and relay attribution stays
unverified. The demo illustrates the proposed measurement workflow and does
not establish a particular relay as the cause of a bottleneck.

Future research can add per-relay limits, stream-to-circuit correlation,
larger modeled networks, and repeated-seed statistical experiments.

The VM box and source commits are pinned. Ubuntu/Python dependencies and Rust's
stable toolchain can still change; this is not a fully frozen software image.

## Stop

```powershell
vagrant halt
```

After exporting results, `vagrant destroy` from this directory removes this
project's VM. Review its confirmation before proceeding.

## Sources

- Shadow 3.3.0: 5a05740bad995b6dbb90b8a16effecf59eceee09
- TGen: 816d68cd3d0ff7d0ec71e8bbbae24ecd6a636117
- TorTriage: de199379534765c2a8a7aaf8c6c1a62a3e160038
- https://shadow.github.io/docs/guide/supported_platforms.html
- https://shadow.github.io/docs/guide/install_dependencies.html
- https://shadow.github.io/docs/guide/getting_started_tor.html
- https://developer.hashicorp.com/vagrant/docs/provisioning/shell
