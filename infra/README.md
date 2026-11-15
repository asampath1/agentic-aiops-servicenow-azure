# Live Azure demo (infra)

The 24-incident evaluation runs on synthetic telemetry (`--telemetry synthetic`). This folder builds a small
**live** environment so one real alert can go through the whole loop: Azure Monitor -> ServiceNow incident ->
triage with real KQL -> approved Azure Automation runbook -> fixed.

| Phase | What | Status |
|---|---|---|
| 1 | Log Analytics workspace, `vm-orders-app-01` (Ubuntu, B2ats_v2, no public IP), Azure Monitor Agent + DCR (Perf, Syslog, Heartbeat), nightly auto-shutdown, optional budget | `main.bicep` |
| 2 | Automation account (managed identity), safe runbooks `RB-VM-Restart-Service`, `RB-VM-Cleanup-Disk` | planned |
| 3 | Alert rules (CPU > 90 %, low disk) -> action group -> Logic App -> ServiceNow incident | planned |
| 4 | Fault scripts (runaway `python3`, disk fill) + `--telemetry azure --automation azure` triage run | planned |

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

## Cost notes

- B2ats_v2 and a 64 GB Premium SSD (P6) are the sizes the Azure free-services list covers; check the
  "Free services" blade in the portal for your remaining hours.
- The workspace has a 0.15 GB/day ingestion cap to stay inside the free allowance.
- No NAT gateway or public IP: the subnet uses default outbound access for the agent and package updates.
- The VM shuts down nightly (22:00 India Standard Time by default).
