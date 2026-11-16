<#
.SYNOPSIS
  KB "Resolving low disk space on Azure VMs" - safe to run automatically with approval.
  Frees space on a Linux demo VM: vacuums the systemd journal, cleans the apt cache, and truncates
  application logs over 100 MB under /var/log (the usual cause: log rotation disabled after patching).

.PARAMETER ResourceName    VM name (the incident's CI), e.g. vm-orders-app-01
.PARAMETER IncidentNumber  ServiceNow incident, for the job log
.PARAMETER ServiceName     accepted for a uniform interface; unused

Guards: acts only on VMs tagged dataset=SYNTH-SKR in the configured resource group, Linux only.
Never deletes files: oversized logs are truncated in place (a 1 MB tail is kept next to them).
#>
param(
    [Parameter(Mandatory = $true)][string] $ResourceName,
    [string] $IncidentNumber = "",
    [string] $ServiceName = ""
)
$ErrorActionPreference = "Stop"

Connect-AzAccount -Identity | Out-Null
$rg = Get-AutomationVariable -Name 'TargetResourceGroup'
$vm = Get-AzVM -ResourceGroupName $rg -Name $ResourceName
if ($vm.Tags['dataset'] -ne 'SYNTH-SKR') { throw "VM $ResourceName is not a SYNTH-SKR demo VM; refusing." }
if ($vm.StorageProfile.OsDisk.OsType -ne 'Linux') { throw "VM $ResourceName is not Linux; this runbook is Linux-only." }

Write-Output "[$IncidentNumber] RB-VM-Cleanup-Disk on $ResourceName"

$script = @'
#!/bin/bash
set -u
echo "before:"; df -h / | tail -1
journalctl --vacuum-size=100M 2>&1 | tail -1
apt-get clean && echo "apt cache cleaned"
find /var/log -xdev -type f -name '*.log' -size +100M 2>/dev/null | while read -r f; do
  sz=$(du -h "$f" | cut -f1)
  tail -c 1048576 "$f" > "$f.tail" && truncate -s 0 "$f"
  echo "truncated $f ($sz), last 1 MB kept in $f.tail"
done
logger -p user.notice -t skr-runbook "RB-VM-Cleanup-Disk completed"
echo "after:"; df -h / | tail -1
'@

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) "rb-cleanup-$([guid]::NewGuid()).sh"
Set-Content -Path $tmp -Value $script -NoNewline
try {
    $r = Invoke-AzVMRunCommand -ResourceGroupName $rg -VMName $ResourceName -CommandId 'RunShellScript' -ScriptPath $tmp
    $msg = ($r.Value | ForEach-Object { $_.Message }) -join "`n"
    Write-Output $msg
    # Run Command returns no exit code: treat anything on stderr as a failed remediation.
    if ($msg -match '\[stderr\]\s*\S') { throw "Script on $ResourceName reported errors (see stderr above); remediation NOT confirmed." }
}
finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
