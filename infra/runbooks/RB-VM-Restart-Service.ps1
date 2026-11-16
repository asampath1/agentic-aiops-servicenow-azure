<#
.SYNOPSIS
  KB "Troubleshooting high CPU on Azure VMs" - safe to run automatically with approval.
  Restarts the named systemd service, or stops the named runaway process, on a Linux demo VM.

.PARAMETER ResourceName    VM name (the incident's CI), e.g. vm-orders-app-01
.PARAMETER IncidentNumber  ServiceNow incident, for the job log
.PARAMETER ServiceName     systemd unit or process name from the Diagnostics agent's signals (e.g. python3)

Guards: acts only on VMs tagged dataset=SYNTH-SKR in the configured resource group, Linux only,
never on system processes, and only on processes using more than 50% CPU.
The job FAILS if the script on the VM writes anything to stderr (Run Command returns no exit code).
#>
param(
    [Parameter(Mandatory = $true)][string] $ResourceName,
    [string] $IncidentNumber = "",
    [string] $ServiceName = ""
)
$ErrorActionPreference = "Stop"

if ($ServiceName -notmatch '^[A-Za-z0-9_.@-]{1,64}$') {
    throw "ServiceName '$ServiceName' is missing or not a plain service/process name; refusing."
}
$protected = @('systemd', 'init', 'sshd', 'ssh', 'walinuxagent', 'waagent', 'python3-waagent', 'azuremonitoragent',
               'mdsd', 'amacoreagent', 'agentlauncher', 'cron', 'rsyslog', 'systemd-journald', 'dbus', 'snapd')
if ($protected -contains $ServiceName.ToLower()) { throw "ServiceName '$ServiceName' is a protected system process; refusing." }

Connect-AzAccount -Identity | Out-Null
$rg = Get-AutomationVariable -Name 'TargetResourceGroup'
$vm = Get-AzVM -ResourceGroupName $rg -Name $ResourceName
if ($vm.Tags['dataset'] -ne 'SYNTH-SKR') { throw "VM $ResourceName is not a SYNTH-SKR demo VM; refusing." }
if ($vm.StorageProfile.OsDisk.OsType -ne 'Linux') { throw "VM $ResourceName is not Linux; this runbook is Linux-only." }

Write-Output "[$IncidentNumber] RB-VM-Restart-Service on $ResourceName, target '$ServiceName'"

# Single-quoted here-string: no PowerShell expansion, so the bash below is exactly what runs.
# __NAME__ is replaced with the validated ServiceName (letters, digits, _ . @ - only).
$template = @'
#!/bin/bash
set -u
NAME='__NAME__'
echo "before: load $(cut -d' ' -f1-3 /proc/loadavg)"
if systemctl list-unit-files --type=service --no-legend | awk '{print $1}' | grep -qx "${NAME}.service"; then
  systemctl restart "${NAME}.service" && echo "restarted service ${NAME}.service"
else
  PIDS=$(ps -eo pid=,pcpu=,comm= | awk -v n="$NAME" '$3==n && $2>50 {print $1}')
  if [ -z "$PIDS" ]; then echo "no '$NAME' process above 50% CPU; nothing to do"; exit 0; fi
  for p in $PIDS; do
    echo "stopping pid $p: $(ps -o pcpu=,args= -p "$p" | cut -c1-80)"
    kill -TERM "$p"
  done
  sleep 5
  for p in $PIDS; do
    if kill -0 "$p" 2>/dev/null; then echo "pid $p still running, SIGKILL"; kill -KILL "$p"; fi
  done
  logger -p user.notice -t skr-runbook "RB-VM-Restart-Service stopped runaway $NAME (pids $(echo $PIDS))"
fi
sleep 10
echo "after: load $(cut -d' ' -f1-3 /proc/loadavg)"
ps -eo pid,pcpu,comm --sort=-pcpu | head -4
'@
$script = $template.Replace('__NAME__', $ServiceName)

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) "rb-restart-$([guid]::NewGuid()).sh"
Set-Content -Path $tmp -Value $script -NoNewline
try {
    $r = Invoke-AzVMRunCommand -ResourceGroupName $rg -VMName $ResourceName -CommandId 'RunShellScript' -ScriptPath $tmp
    $msg = ($r.Value | ForEach-Object { $_.Message }) -join "`n"
    Write-Output $msg
    if ($msg -match '\[stderr\]\s*\S') { throw "Script on $ResourceName reported errors (see stderr above); remediation NOT confirmed." }
}
finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
