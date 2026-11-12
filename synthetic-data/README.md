# Synthetic enterprise ITSM data: ShopKart Retails (SKR)

A realistic, **entirely fictional** ITSM dataset for practising AI and multi-agent operations on a
ServiceNow Personal Developer Instance (PDI).

**Company:** ShopKart Retails (SKR), a fictional retailer running its stack on Azure, supported by a managed-services team.
Every record is tagged `SYNTH-SKR` (in `correlation_id` or the description), and every user name starts with `synth.`.

## What you get (default run)

| Table | Records | Notes |
|---|---|---|
| sys_user | 75 | 34 IT engineers, 40 business users, 1 Azure Monitor service account |
| sys_user_group / grmember | 10 / 34 | `SKR Service Desk L1`, `SKR Azure Infra Ops`, `SKR Azure Database Ops`, … |
| cmdb_ci_service | 7 | E-Commerce Storefront, Order Processing, Payments, HR Portal, Data & Analytics, Identity, Shared Platform |
| CIs (win/linux server, SQL, appl, firewall) | 28 | Azure-style names: `vm-ecom-web-01`, `sql-orders-prod`, `func-orders-processor`, `aks-platform-prod` … |
| cmdb_rel_ci | 42 | service → CI, plus app → DB/cache/Key Vault dependencies (blast-radius analysis) |
| kb_knowledge | 20 | One per failure pattern: symptoms, cause, steps, **runbook name**, safe-to-automate flag |
| change_request | ~73 | Monthly patching, releases, NSG updates, secret rotations, some of which **caused incidents** |
| problem | 4 | Known errors with linked incidents (Storefront memory leak, Orders DTU, cert renewal, Entra sync) |
| incident | 320 | 296 resolved/closed with work notes and root cause, plus **24 OPEN incidents = evaluation set** |

There are 18 recurring Azure failure patterns: high CPU, disk full, IIS memory leak, App Service 5xx,
SQL DTU exhaustion, SQL blocking, certificate expiry, backup failure, VM stuck after patching, NSG blocking,
Key Vault 403, Entra Connect sync, storage throttling, AKS CrashLoopBackOff, Function/queue backlog,
VPN tunnel down, expired service-principal secret and Data Factory pipeline failure. About 12% of incidents are
service-desk "noise" (password resets, Outlook and so on) that a triage agent should route to L1 and never
auto-remediate.

`data/ground_truth.json` is the answer key for the 24 open incidents. For each one it gives the correct
group, root cause, KB article, runbook, whether it is safe to automate, and the related change and problem.
**Don't load it into ServiceNow or show it to your agents.** Use it to score them.

## Steps

```bash
pip install requests

# 1. (optional) regenerate: different size/seed
cd synthetic-data
python3 generate_data.py --days 180 --incidents 320 --eval 24 --seed 42

# 2. wake your PDI (log in once in the browser), then set credentials
export SN_INSTANCE=dev123456          # your PDI name
export SN_USER=admin
export SN_PASSWORD='********'

# 3. check offline that every reference resolves
python3 load_to_snow.py --dry-run

# 4. load (≈ 900 API calls, ~10-20 min on a PDI)
python3 load_to_snow.py
#    resumable: re-run after any error; already-created records are skipped

# 5. remove everything later
python3 load_to_snow.py --cleanup
```

On Windows PowerShell, use `$env:SN_INSTANCE="dev123456"` and so on instead of `export`.

After loading, `data/ground_truth.loaded.json` maps each eval incident to its real INC/CHG/PRB numbers.

### Verify in ServiceNow
- Incidents: `incident.list` filter **Correlation ID = SYNTH-SKR**
- Open evaluation set: same filter plus **State = New** (the assignment group is intentionally blank, so routing is your agent's job)
- Changes that caused incidents: open an incident and look at the **Caused by Change** field
- KB: Knowledge > IT knowledge base, search "Azure"

## Notes and gotchas
- **Close codes.** The script uses `Solution provided`, `Workaround provided` and `Resolved by change`,
  which are the values in recent releases. If your instance uses older values (for example, `Solved (Permanently)`), check
  `sys_choice` for `incident.close_code` and edit the mapping in `generate_data.py`.
- **State models.** If the change or problem state model rejects a direct `Closed` state, the loader retries
  without the state fields, so the record is still created (as New).
- **Timestamps.** `opened_at`, `resolved_at` and `closed_at` are set with a second call after insert, so the 6-month
  history is realistic for trend and change-correlation analysis.
- **Unknown fields** are silently ignored by the Table API, so differences between releases won't break the load.
- The PDI hibernates after inactivity and is reclaimed if unused for about 10 days. Log in first, and keep `manifest.json`.

## How this feeds a multi-agent design

| Agent | Uses from this data |
|---|---|
| **Triage / Router** | short_description, description, CI → predict `assignment_group`, priority, noise vs infra |
| **Knowledge (RAG)** | 20 KB articles + 296 resolved incidents (work notes, close notes) → similar incidents and fix steps |
| **Change correlation** | change_request on the same CI in the last 24-48 h → "likely caused by CHG…" |
| **Diagnostics** | Alert text plus log snippets in the description (pair with your real Azure Log Analytics later) |
| **Problem / Trend** | Recurring patterns per CI → link to the existing problem or propose a new one |
| **Remediation** | Runbook name plus safe-to-automate flag from the KB → run an Azure Automation runbook **only with human approval** |
| **Communicator** | Writes work notes and resolution back to the incident |

Score your system on the 24 open incidents for routing accuracy, root-cause match, correct KB, correct runbook,
change detected, and "never auto-ran an unsafe runbook".
