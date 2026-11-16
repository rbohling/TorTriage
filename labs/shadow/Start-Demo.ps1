param(
    [ValidateSet('baseline', 'latency', 'both')]
    [string]$Mode = 'baseline'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$vagrantCommand = Get-Command vagrant.exe -ErrorAction SilentlyContinue
$vagrantExe = if ($vagrantCommand) { $vagrantCommand.Source } else {
    'C:\Program Files\Vagrant\bin\vagrant.exe'
}
$vboxExe = 'C:\Program Files\Oracle\VirtualBox\VBoxManage.exe'
foreach ($executable in @($vagrantExe, $vboxExe)) {
    if (-not (Test-Path -LiteralPath $executable)) {
        throw "Required program was not found: $executable"
    }
}

function Invoke-VagrantChecked {
    param([string[]]$Arguments)
    & $vagrantExe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Vagrant failed (exit $LASTEXITCODE): $($Arguments -join ' ')"
    }
}

Push-Location -LiteralPath $PSScriptRoot
try {
    Write-Host 'Checking VirtualBox access before making changes...'
    & $vboxExe list vms | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'VirtualBox command access failed. No VM was started by this launcher.'
    }
    Invoke-VagrantChecked -Arguments @('validate')
    Invoke-VagrantChecked -Arguments @('up', '--provider=virtualbox')

    $scenarios = if ($Mode -eq 'both') { @('baseline', 'latency') } else { @($Mode) }
    foreach ($scenario in $scenarios) {
        Invoke-VagrantChecked -Arguments @(
            'ssh', '-c', "python3 ~/shadow-lab/demo.py $scenario"
        )
    }
    Write-Host 'Requested simulation checks passed. Reports: ~/shadow-lab/results/ in the VM.'
    Write-Host "Stop the VM later with: vagrant halt (from $PSScriptRoot)"
}
finally {
    Pop-Location
}
