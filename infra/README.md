# Live Azure demo (infra)

The 24-incident evaluation runs on synthetic telemetry (`--telemetry synthetic`). This folder builds a small
**live** environment so one real alert can go through the whole loop: Azure Monitor -> ServiceNow incident ->
triage with real KQL -> approved Azure Automation runbook -> fixed.

| Phase | What | Status |
|---|---|---|
| 1 | Log Analytics workspace, `vm-orders-app-01` (Ubuntu, B2ats_v2, no public IP), Azure Monitor Agent + DCR (Perf, Syslog, Heartbeat), nightly auto-shutdown, optional budget | deployed |
| 2 | Automation account `aa-skr-aiops` (managed identity, custom role: VM read + Run Command on this RG only, local auth off), safe runbooks `RB-VM-Restart-Service`, `RB-VM-Cleanup-Disk`, job logs to the workspace | deployed |
| 3 | `alerts.bicep` (separate deploy, needs ServiceNow creds): `vm-cpu-high` (metric, CPU > 90 % / 15 min), `vm-disk-low` (log, `/` < 10 % free) -> action group `ag-skr-servicenow` -> Logic App `la-skr-alert-to-snow` -> ServiceNow incident (`correlation_id=SYNTH-SKR-LIVE`); resolved alerts add a work note | deployed |
| 4 | `faults/inject.sh` (runaway `python3`, disk fill) + `--live --telemetry azure --automation azure` triage run, auto-resolve | done 2026-11-16 (CPU + disk) |

## Running the live loop

```bash
infra/faults/inject.sh cpu        # or: disk. Alert fires after ~15 min (CPU) / ~10 min (disk)
# when the Logic App has created the SYNTH-SKR-LIVE incident (zsh with SN_* set):
export LOG_ANALYTICS_WORKSPACE_ID=<workspace id> AZURE_SUBSCRIPTION_ID=$(az account show --query id -o tsv) \
       AUTOMATION_RESOURCE_GROUP=rg-skr-aiops-demo AUTOMATION_ACCOUNT=aa-skr-aiops
python -m agents --source servicenow --live --telemetry azure --automation azure --approver interactive \
       --write --out runs/live -v       # approve the proposed runbook at the prompt
infra/faults/inject.sh status     # confirm; `clear` resets manually without the runbook
```

## Incident lifecycle (live alerts)

| Event | Incident |
|---|---|
| Alert fires | Logic App creates it: **New**, `correlation_id=SYNTH-SKR-LIVE` |
| `--live --write` triage | work note + assignment group, **In Progress** |
| Alert clears **and** a Completed runbook job for this incident started after the alert fired | **Resolved**, close code `Auto-remediated (AIOps)`, close notes name the job(s) |
| Alert clears, no such job | stays In Progress, work note "needs review: symptom may have cleared on its own" |

Filter auto-fixed incidents with *State = Resolved AND Close code = Auto-remediated (AIOps)*. The close-code choice is
added once with `python3 infra/servicenow/add_close_code.py --apply`. The Logic App reads job history with its own
managed identity (Reader on the Automation account; it cannot start jobs). Runbooks fail on any stderr, so a broken fix
never counts as Completed.

## Runs on 2026-11-16

- **CPU**: alert fired 06:42Z, INC0010598, triage proposed RB-VM-Restart-Service with `ServiceName=python3` (from the
  real Syslog), approved; the first job "Completed" while its bash failed (PowerShell quoting; since fixed, and runbooks
  now fail on stderr); the fixed job stopped the runaway; alert resolved 06:55Z. Auto-resolve was added afterwards and
  verified by replaying that resolved alert.
- **Disk**: injected 07:53Z, alert fired ~08:10Z, INC0010599, triage (In Progress) proposed RB-VM-Cleanup-Disk, approved;
  job truncated the 55 GB log (96% -> 5% used); alert cleared 08:35Z; incident auto-resolved with the close code.

The VM is named after a CMDB CI that already has history for both runbooks, so the remediation guard
(runbook must have run on this CI or CI class before) allows them.

## Prerequisites

- `az login` (a free-trial subscription with the spending limit on is enough; Central India offers B2ats_v2 to it).
- Providers registered: Compute, Network, Storage, OperationalInsights, Insights, Automation, Logic, DevTestLab.
- An SSH public key. It is only put on the VM (there is no public IP; commands run through Run Command):
  `ssh-keygen -t ed25519 -N "" -C skr-aiops-demo -f ~/.ssh/skr_aiops_demo`

## Preview, deploy, verify, tear down

```bash
# Preview (creates nothing)
az deployment sub what-if -l centralindia -n skr-aiops-demo -f infra/main.bicep \
  -p adminSshPublicKey="$(cat ~/.ssh/skr_aiops_demo.pub)"

# Deploy (add budgetContactEmail=you@example.com to get budget alerts)
az deployment sub create -l centralindia -n skr-aiops-demo -f infra/main.bicep \
  -p adminSshPublicKey="$(cat ~/.ssh/skr_aiops_demo.pub)"

# Upload + publish the runbook bodies (infra/runbooks/*.ps1); re-run after editing one
infra/publish-runbooks.sh

# Phase 3 alerts -> ServiceNow (zsh; the password is stored as a SecureString Logic App parameter)
az deployment group create -g rg-skr-aiops-demo -n skr-aiops-alerts -f infra/alerts.bicep \
  -p snInstance="$SN_INSTANCE" snUser="$SN_USER" snPassword="$SN_PASSWORD"

# Workspace id for the agents (LOG_ANALYTICS_WORKSPACE_ID)
az deployment sub show -n skr-aiops-demo --query properties.outputs.workspaceId.value -o tsv

# Data arriving? (allow ~10 minutes after deploy)
az monitor log-analytics query -w <workspace id> \
  --analytics-query "Heartbeat | summarize max(TimeGenerated) by Computer" -o table

# Start the VM after the nightly auto-shutdown
az vm start -g rg-skr-aiops-demo -n vm-orders-app-01

# Tear down everything (the budget, if created, is subscription-level: delete it separately)
az group delete -n rg-skr-aiops-demo --yes
az consumption budget delete --budget-name budget-skr-aiops-demo
```

## Runbook guards

Both runbooks act only on VMs in `TargetResourceGroup` tagged `dataset=SYNTH-SKR`, Linux only.
`RB-VM-Restart-Service` refuses system processes (sshd, waagent, the monitoring agent, systemd, ...) and only stops
processes above 50 % CPU. `RB-VM-Cleanup-Disk` never deletes files: it vacuums the journal, cleans the apt cache and
truncates `/var/log/**/*.log` over 100 MB (keeping the last 1 MB).

## Alert -> incident format

The Logic App writes incidents in the same shape as the 235 historical Azure Monitor incidents, so retrieval matches:
title `[Azure Monitor] Sev2 - <rule description>`, description starting `Auto-generated by Azure Monitor action group.` /
`Alert rule: ...` / `Resource: ...`, CI linked by name, caller `synth.svc.azuremonitor`, impact/urgency 2. The alert id
goes in `correlation_display`; a `Resolved` alert finds the incident by it and adds a work note.
Live incidents use `correlation_id=SYNTH-SKR-LIVE` so they never join the 24-incident eval set (`SYNTH-SKR`).

## Free-trial limits met so far

- VM sizes: B1s/B2s are blocked; B2ats_v2 / B2als_v2 work in Central India, non-zonal only.
- Automation accounts can only be created in eastus, eastus2, westus, northeurope, southeastasia, japanwest, so the
  account lives in Southeast Asia (`automationLocation`); Run Command works across regions.
- 4 vCPUs per region.

## Cost notes

- B2ats_v2 and a 64 GB Premium SSD (P6) are the sizes the Azure free-services list covers; check the
  "Free services" blade in the portal for your remaining hours.
- The workspace has a 0.15 GB/day ingestion cap to stay inside the free allowance.
- No NAT gateway or public IP: the subnet uses default outbound access for the agent and package updates.
- The VM shuts down nightly (22:00 India Standard Time by default).
